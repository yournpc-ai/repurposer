"""A fresh design waits for its existing queued website instead of claiming no source."""
from uuid import uuid4
import pytest
from app.models.tables import User,Project,Asset,SourceSnapshot
from app.models.schemas import AssetType,AssetStatus
from app.tools.video import design

pytestmark=pytest.mark.asyncio


async def test_pending_webpage_is_requested_and_reused_without_duplicate_asset(database,monkeypatch):
    async with database() as db:
        user=User(email=f'{uuid4()}@test.local');db.add(user);await db.flush()
        project=Project(user_id=user.id,title='pending site');db.add(project);await db.flush()
        asset=Asset(user_id=user.id,project_id=project.id,type=AssetType.WEB_PAGE,
                    processing_status=AssetStatus.PENDING,meta={'capture_url':'https://example.com/'})
        db.add(asset);await db.commit();uid,pid,aid=user.id,project.id,asset.id
    monkeypatch.setattr(design,'AsyncSessionLocal',database)
    waits=[]
    async def worker(db,origin,**kw):
        assert origin==pid and kw['asset_ids']=={aid};waits.append(origin)
        async with database() as other:
            row=await other.get(Asset,aid)
            assert row.processing_requested_at is not None
            row.processing_status=AssetStatus.COMPLETED
            row.meta={'capture_url':'https://example.com/','shots':[{'view_id':'view-0'}]}
            await other.commit()
    monkeypatch.setattr(design,'_await_captures_settled',worker)
    async with database() as db:
        result=await design._ready_web_pages(db,project_id=pid,owner_id=uid)
        assert [a.id for a in result]==[aid] and waits==[pid]
        # A second design sees the already-ready page and doesn't queue or wait again.
        again=await design._ready_web_pages(db,project_id=pid,owner_id=uid)
        assert [a.id for a in again]==[aid] and len(waits)==1


async def test_prepared_snapshot_commits_before_a_later_design_failure(database,monkeypatch):
    from sqlalchemy import select
    from app.models.tables import SourceSnapshot
    from app.models.schemas import PrepareVideoMaterialsArgs

    async with database() as db:
        user=User(email=f'{uuid4()}@test.local');db.add(user);await db.flush()
        project=Project(user_id=user.id,title='prepared media');db.add(project);await db.flush()
        asset=Asset(user_id=user.id,project_id=project.id,type=AssetType.IMAGE,
                    processing_status=AssetStatus.COMPLETED,file_url='source-snapshots/image.png')
        db.add(asset);await db.commit();uid,pid,aid=user.id,project.id,asset.id
    monkeypatch.setattr(design,'AsyncSessionLocal',database)

    async def freeze(db, asset, *, owner_id):
        snapshot=SourceSnapshot(owner_id=owner_id,asset_id=asset.id,kind='image',
            storage_key=asset.file_url,digest='a'*64,meta={'width':640,'height':360})
        db.add(snapshot);await db.flush();return snapshot
    monkeypatch.setattr(design,'snapshot_image_asset',freeze)
    async def no_media(*args,**kwargs): return []
    monkeypatch.setattr(design,'_fixed_media_inputs',no_media)
    facts,images=await design.prepare_video_materials(owner_id=uid,project_id=pid,
        args=PrepareVideoMaterialsArgs(material_asset_ids=[aid]))
    assert not images and facts['resources'][0]['digest']=='a'*64
    # A subsequent candidate rejection has no transaction power over this commit.
    with pytest.raises(design.DesignError):
        raise design.DesignError('candidate rejected')
    async with database() as db:
        stored=await db.scalar(select(SourceSnapshot).where(SourceSnapshot.asset_id==aid))
        assert stored is not None and stored.digest=='a'*64


async def test_library_music_preparation_has_distinct_identity_permissions_and_public_context(database,monkeypatch):
    from sqlalchemy import select
    from app.models.tables import Music,SourceSnapshot
    from app.models.schemas import PrepareVideoMaterialsArgs
    from app.tools.project_context import load_project_context
    from app.editing.timing import SOURCE_TIMEBASE
    async with database() as db:
        owner=User(email=f'{uuid4()}@test.local');other=User(email=f'{uuid4()}@test.local')
        db.add_all([owner,other]);await db.flush()
        project=Project(user_id=owner.id,title='music');db.add(project)
        common=dict(ext='mp3',file_path='music/test.mp3',size_bytes=100,duration_seconds=12)
        public=Music(mood=uuid4().hex,title='Public',is_public=True,**common)
        private=Music(mood=uuid4().hex,title='Own',is_public=False,generated_by_user_id=owner.id,**common)
        inaccessible=Music(mood=uuid4().hex,title='Other',is_public=False,generated_by_user_id=other.id,**common)
        db.add_all([public,private,inaccessible]);await db.commit()
        uid,pid=owner.id,project.id
        public_id,private_id,blocked_id=public.id,private.id,inaccessible.id
    monkeypatch.setattr(design,'AsyncSessionLocal',database)
    async def freeze(db,track,*,owner_id):
        found=await db.scalar(select(SourceSnapshot).where(SourceSnapshot.owner_id==owner_id,SourceSnapshot.meta['music']['music_id'].astext==str(track.id)))
        if found:return found
        snapshot=SourceSnapshot(owner_id=owner_id,kind='audio',digest='b'*64,
            storage_key='source-snapshots/audio.mp3',duration_ticks=12*SOURCE_TIMEBASE,
            meta={'music':{'music_id':str(track.id),'title':track.title}})
        db.add(snapshot);await db.flush();return snapshot
    monkeypatch.setattr(design,'snapshot_music_track',freeze)
    async def no_media(*args,**kwargs):return []
    monkeypatch.setattr(design,'_fixed_media_inputs',no_media)
    args=PrepareVideoMaterialsArgs(material_music_ids=[public_id,private_id])
    facts,images=await design.prepare_video_materials(owner_id=uid,project_id=pid,args=args)
    assert not images and len(facts['resources'])==2
    assert all(resource['kind']=='audio' for resource in facts['resources'])
    assert all(resource['clip_source']=={
        'snapshot_id':resource['snapshot_id'],
        'snapshot_digest':resource['digest'],
        'source_range':{'start':0,'end':12*SOURCE_TIMEBASE},
    } for resource in facts['resources'])
    again,_=await design.prepare_video_materials(owner_id=uid,project_id=pid,args=args)
    assert [r['snapshot_id'] for r in again['resources']]==[r['snapshot_id'] for r in facts['resources']]
    async with database() as db:
        context=await load_project_context(db,project_id=pid,owner_id=uid)
        assert set(facts['context_keys']).issubset(context.keys)
    with pytest.raises(design.DesignError,match='public or user-owned'):
        await design.prepare_video_materials(owner_id=uid,project_id=pid,args=PrepareVideoMaterialsArgs(material_music_ids=[blocked_id]))
    with pytest.raises(design.DesignError,match='material asset'):
        await design.prepare_video_materials(owner_id=uid,project_id=pid,args=PrepareVideoMaterialsArgs(material_asset_ids=[public_id]))


async def test_real_music_bytes_freeze_once_and_reuse_across_owned_chats(database,monkeypatch):
    import io
    import av
    from app.tools.video import preparation
    from app.models.tables import Music,SourceSnapshot
    from app.models.schemas import PrepareVideoMaterialsArgs
    from sqlalchemy import select
    buf=io.BytesIO();container=av.open(buf,mode='w',format='mp3')
    stream=container.add_stream('libmp3lame',rate=44100);stream.layout='mono'
    frame=av.AudioFrame(format='s16p',layout='mono',samples=4410);frame.sample_rate=44100
    for plane in frame.planes:plane.update(bytes(plane.buffer_size))
    for packet in stream.encode(frame):container.mux(packet)
    for packet in stream.encode(None):container.mux(packet)
    container.close();audio=buf.getvalue()
    async with database() as db:
        owner=User(email=f'{uuid4()}@test.local');db.add(owner);await db.flush()
        a=Project(user_id=owner.id,title='A');b=Project(user_id=owner.id,title='B')
        track=Music(mood=uuid4().hex,title='Real local fixture',ext='mp3',file_path='music/fixture.mp3',size_bytes=len(audio),is_public=True)
        db.add_all([a,b,track]);await db.commit();uid,pa,pb,mid=owner.id,a.id,b.id,track.id
    objects={track.file_path:audio}
    async def read(key):return objects[key]
    async def exists(key):return key in objects
    async def save(key,data,**kwargs):objects[key]=data
    monkeypatch.setattr(preparation.storage,'read',read)
    monkeypatch.setattr(preparation.storage,'exists',exists)
    monkeypatch.setattr(preparation.storage,'save',save)
    monkeypatch.setattr(design,'AsyncSessionLocal',database)
    args=PrepareVideoMaterialsArgs(material_music_ids=[mid])
    from app.agents.tool_progress import ToolProgress, bind_progress
    steps = []
    with bind_progress("import", steps.append):
        first, _ = await design.prepare_video_materials(owner_id=uid, project_id=pa, args=args)
    assert steps == [ToolProgress("import", "import_music")]
    repeated,_=await design.prepare_video_materials(owner_id=uid,project_id=pa,args=args)
    other,_=await design.prepare_video_materials(owner_id=uid,project_id=pb,args=args)
    ids=[r['resources'][0]['snapshot_id'] for r in (first,repeated,other)]
    assert ids[0]==ids[1]==ids[2]
    async with database() as db:
        row=await db.scalar(select(SourceSnapshot).where(SourceSnapshot.owner_id==uid))
        assert row.origin_project_id==pa and row.kind=='audio' and row.duration_ticks>0
        assert row.meta['music']['music_id']==str(mid)
        assert objects[row.storage_key]==audio


async def test_completed_partial_capture_reuses_digest_without_reset(database, monkeypatch):
    from app.pipeline import jobs
    from app.pipeline.assets import create_capture_plan_asset_committed
    from app.tools.research.capture import CapturePlan, capture_plan_digest

    plan = CapturePlan(
        source_url='https://example.com/', source_snapshot_id=uuid4(),
        states=[{'state_id': 'settled'}],
        artifacts=[{'artifact_id': 'page', 'state_id': 'settled', 'role': 'view', 'required': False}],
    )
    digest = capture_plan_digest(plan)
    async with database() as db:
        user = User(email=f'{uuid4()}@test.local')
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title='partial capture')
        db.add(project)
        await db.flush()
        asset = Asset(
            user_id=user.id, project_id=project.id, type=AssetType.WEB_PAGE,
            processing_status=AssetStatus.COMPLETED,
            meta={
                'capture_url': plan.capture_url, 'capture_plan_digest': digest,
                'capture_issues': [{'state_id': 'settled', 'output_id': 'missing', 'error': 'absent'}],
                'shots': [{'view_id': 'page', 'key': 'source-snapshots/page.png'}],
            },
        )
        db.add(asset)
        await db.commit()
        uid, pid, aid = user.id, project.id, asset.id
    monkeypatch.setattr('app.models.database.AsyncSessionLocal', database)

    def unexpected_reset(_asset):
        raise AssertionError('completed partial capture must not reset')

    monkeypatch.setattr(jobs, 'reset_asset_processing', unexpected_reset)
    assert await create_capture_plan_asset_committed(pid, uid, plan) == aid
    async with database() as db:
        stored = await db.get(Asset, aid)
        assert stored.processing_status == AssetStatus.COMPLETED
        assert stored.meta['capture_issues'][0]['output_id'] == 'missing'


async def test_capture_web_returns_partial_resources_real_images_and_compact_issues(database, monkeypatch):
    from app.tools.research.capture import CaptureRequest

    async with database() as db:
        user = User(email=f'{uuid4()}@test.local')
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title='capture projection')
        db.add(project)
        source = SourceSnapshot(
            owner_id=user.id, kind='web', digest='a' * 64,
            storage_key='source-snapshots/source.json',
            meta={'canonical_url': 'https://example.com/', 'views': []},
        )
        db.add_all([project, source])
        await db.commit()
        uid, pid, source_id = user.id, project.id, source.id
    monkeypatch.setattr(design, 'AsyncSessionLocal', database)
    captured = SourceSnapshot(
        owner_id=uid, kind='web', digest='c' * 64,
        storage_key='source-snapshots/captured.json',
        meta={
            'canonical_url': 'https://example.com/',
            'capture_issues': [{'state_id': 'settled', 'output_id': 'missing', 'error': 'absent'}],
            'capture_issue_count': 70,
            'capture_issues_truncated': True,
            'views': [{
                'view_id': 'page', 'state_id': 'settled', 'output_id': 'page',
                'artifact_role': 'view', 'storage_key': 'source-snapshots/page.png',
                'digest': 'e' * 64, 'width': 100, 'height': 80, 'elements': [],
            }],
        },
    )
    fixed = SourceSnapshot(
        owner_id=uid, kind='image', digest='d' * 64,
        storage_key='source-snapshots/card.png',
        meta={
            'origin': 'web_view', 'artifact_role': 'cutout', 'transparent': False,
            'state_id': 'settled', 'output_id': 'cards', 'target_id': 'cards',
            'member_id': 'cards-m000', 'width': 20, 'height': 10,
        },
    )

    async def execute(db, *, owner_id, project_id, plan):
        assert owner_id == uid and project_id == pid
        assert {artifact.role for artifact in plan.artifacts} == {'view', 'cutout'}
        db.add_all([captured, fixed])
        await db.flush()
        return None, captured

    async def derivatives(*_args, **_kwargs):
        return [fixed]

    async def media(snapshots, _views, *, omitted):
        assert snapshots == [captured] and omitted == []
        return [{'type': 'image', 'storage_key': 'source-snapshots/page.png'}]

    monkeypatch.setattr(design, '_execute_capture_plan', execute)
    monkeypatch.setattr('app.tools.video.preparation.snapshot_web_generator_resources', derivatives)
    monkeypatch.setattr(design, '_view_facts', lambda _snapshots: [])
    monkeypatch.setattr(design, '_view_media_inputs', media)
    request = CaptureRequest.model_validate({
        'source_url': 'https://example.com/', 'source_snapshot_id': source_id,
        'states': [{'state_id': 'settled'}],
        'targets': [{'target_id': 'cards', 'selector': '.card'}],
        'outputs': [
            {'output_id': 'page', 'state_id': 'settled', 'kind': 'page'},
            {'output_id': 'cards', 'state_id': 'settled', 'kind': 'elements', 'target_ids': ['cards']},
        ],
    })
    facts, images = await design.capture_video_web(owner_id=uid, project_id=pid, request=request)
    assert images == [{'type': 'image', 'storage_key': 'source-snapshots/page.png'}]
    assert facts['partial'] is True and facts['issues'][0]['output_id'] == 'missing'
    assert facts['issue_count'] == 70 and facts['issues_truncated'] is True
    assert facts['media_files'] == 1 and facts['media_omitted'] == []
    assert facts['snapshot_id'] == str(captured.id)
    assert facts['context_keys'] == [
        f'snapshot:{captured.id}:{captured.digest}', f'snapshot:{fixed.id}:{fixed.digest}',
    ]
    assert 'lines' not in facts['resources'][0]
    assert 'artifact_role' not in facts['resources'][0]['views'][0]
    assert facts['resources'][1]['fixed_resource']['snapshot_id'] == str(fixed.id)
    assert facts['resources'][1]['member_id'] == 'cards-m000'
    assert 'artifact_role' not in facts['resources'][1]



async def test_default_web_projection_is_compact_and_selected_target_restores_exact_facts():
    from types import SimpleNamespace
    from app.tools.project_context import source_context
    from app.tools.video.preparation import canonical_resource

    view = {
        'view_id': 'hero', 'heading': 'Launch', 'width': 1440, 'height': 900,
        'digest': 'c' * 64, 'storage_key': 'sources/hero.png',
        'elements': [{
            'id': 'title', 'kind': 'heading', 'text': 'Launch', 'x': 0.5, 'y': 0.3,
            'w': 0.6, 'h': 0.15, 'css': {'font': 'serif'}, 'storage_key': 'sources/title.png',
        }],
    }
    snapshot = SourceSnapshot(
        id=uuid4(), owner_id=uuid4(), kind='web', digest='a' * 64,
        storage_key='sources/web.json', meta={'lines': [{'line_id': 'L1', 'text': 'Launch'}], 'views': [view]},
    )
    projected = source_context(snapshot)
    assert 'meta' not in projected and 'elements' not in projected['views'][0]
    assert projected['citable_lines'][0]['line_id'] == 'L1'
    assert projected['views'][0]['targets'][0]['id'] == 'title'
    assert 'css' not in projected['views'][0]['targets'][0]
    default = canonical_resource(snapshot)
    assert 'elements' not in default['views'][0] and 'selected_target' not in default
    selected = canonical_resource(
        snapshot, target=SimpleNamespace(view_id='hero', element_id='title'),
    )
    assert selected['selected_target']['view'] == view


async def test_duplicate_page_asset_text_uses_snapshot_lines_as_single_semantic_seat(database):
    from app.tools.project_context import load_project_context

    body = 'Shared launch evidence'
    async with database() as db:
        user = User(email=f'{uuid4()}@test.local')
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title='dedup')
        db.add(project)
        await db.flush()
        asset = Asset(
            user_id=user.id, project_id=project.id, type=AssetType.WEB_PAGE,
            processing_status=AssetStatus.COMPLETED, extracted_text=body,
            meta={'capture_url': 'https://example.com/'},
        )
        db.add(asset)
        await db.flush()
        snapshot = SourceSnapshot(
            owner_id=user.id, asset_id=asset.id, kind='web', digest='a' * 64,
            storage_key='sources/web.json',
            meta={
                'canonical_url': 'https://example.com/',
                'lines': [
                    {'line_id': 'L1', 'text': 'Shared launch'},
                    {'line_id': 'L2', 'text': 'evidence'},
                ],
                'views': [],
            },
        )
        from app.models.tables import PageReading
        db.add_all([snapshot, PageReading(project_id=project.id, url='https://example.com', text=body)])
        await db.commit()
        context = await load_project_context(db, project_id=project.id, owner_id=user.id)
    assert body not in context.text
    assert context.text.count('Shared launch') == 1
    assert context.text.count('text_snapshot_id') == 2


async def test_covered_history_media_folds_and_read_by_id_restores_original(database, monkeypatch):
    from app.chat import conversation_context
    from app.chat.conversation_context import ConversationContext, ReadConversationContextArgs, select_items
    from app.models.tables import Conversation, Message

    monkeypatch.setattr(conversation_context, 'AsyncSessionLocal', database)

    turn_id = uuid4()
    item = {
        'id': f'{turn_id}:0:0:call', 'turn_id': str(turn_id), 'tool': 'prepare_video_materials',
        'arguments': {}, 'executed_arguments': {}, 'text': 'full original observation', 'ok': True,
        'media_refs': [{'type': 'image', 'mime': 'image/png', 'url': 'https://example.com/image.png'}],
        'resource_keys': ['snapshot:source:digest'], 'lifetime': 'project',
        'project_text': 'compact project facts', 'persist': True, 'skill_reference': None,
        'base_versions': [], 'target_tool': None, 'candidate': None,
    }
    stale_version = {
        **item, 'id': f'{turn_id}:1:0:version', 'tool': 'get_video_version',
        'media_refs': [], 'resource_keys': ['composition:old-version:old-digest'],
        'project_text': 'compact version facts',
    }
    selected, omitted = select_items(
        [item, stale_version], current_turn=uuid4(), valid_turns={str(turn_id): 'original'},
        keys=frozenset({'snapshot:source:digest', 'composition:current:digest'}),
        skill_reference=None, budget=10000,
    )
    assert [entry['id'] for entry in omitted] == [stale_version['id']]
    assert selected[0]['text'] == 'compact project facts'
    assert selected[0]['media_refs'] == [] and item['media_refs']

    async with database() as db:
        user = User(email=f'{uuid4()}@test.local')
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title='history')
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id, context={'schema_version': 1, 'items': [item]})
        db.add(conversation)
        await db.flush()
        db.add(Message(id=turn_id, conversation_id=conversation.id, role='user', content='original', turn_state='settled'))
        await db.commit()
        conversation_id = conversation.id
    context = ConversationContext(conversation_id=conversation_id, owner_id=user.id, turn_id=uuid4())
    async def media(found):
        assert found[0]['media_refs'] == item['media_refs']
        return ('original media',), []
    monkeypatch.setattr(context, '_media', media)
    restored = await context.read(ReadConversationContextArgs(item_ids=[item['id']]))
    assert restored.images == ('original media',)
    assert 'full original observation' in restored.text


async def test_nonstreaming_skill_read_receipt_lands_in_conversation_context(database, monkeypatch):
    from app.agents.tool_loop import ToolExchange, ToolObservation
    from app.chat import conversation_context
    from app.chat.activity_receipts import SkillReadReceipt
    from app.chat.conversation_context import ConversationContext
    from app.models.tables import Conversation, Message
    from app.tools.project_context import settled_skill_read_receipts
    from sqlalchemy import select

    monkeypatch.setattr(conversation_context, 'AsyncSessionLocal', database)
    monkeypatch.setattr('app.models.database.AsyncSessionLocal', database)
    async with database() as db:
        user = User(email=f'{uuid4()}@test.local')
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title='receipt')
        db.add(project)
        await db.flush()
        conversation = Conversation(user_id=user.id, project_id=project.id)
        db.add(conversation)
        await db.flush()
        turn = Message(
            conversation_id=conversation.id, role='user', content='read', turn_state='in_flight',
        )
        db.add(turn)
        await db.commit()
        uid, pid, cid, tid = user.id, project.id, conversation.id, turn.id
    skill = {'kind': 'builtin', 'skill_id': 'promo-video', 'version': '1.0.0'}
    receipt = SkillReadReceipt(
        package_identity='promo-video:1.0.0', skill_reference=skill, owner_id=str(uid),
        reads=[{
            'path': 'references/sequences/product-evidence.md', 'digest': 'a' * 64,
            'kind': 'reference', 'offset': 0, 'truncated': False,
        }],
        preview_checks=[{'shot_id': 'evidence-push', 'available': True}], media_files=1,
    )
    context = ConversationContext(conversation_id=cid, owner_id=uid, turn_id=tid)
    await context.record(ToolExchange(
        call_id='read-1', tool_name='read_skill_reference', arguments={},
        observation=ToolObservation('read', receipt=receipt),
    ))
    async with database() as db:
        turn = await db.get(Message, tid)
        turn.turn_state = 'settled'
        await db.commit()
        merged = await settled_skill_read_receipts(db, project_id=pid, owner_id=uid)
        stored = await db.get(Conversation, cid)
        activity_rows = list((await db.scalars(select(Message).where(
            Message.conversation_id == cid,
            Message.intent['type'].astext == 'activity',
        ))).all())
    assert merged['promo-video:1.0.0']['reads'] == receipt.reads
    assert merged['promo-video:1.0.0']['preview_checks'] == receipt.preview_checks
    assert stored.context['items'][0]['receipt'] == receipt.model_dump(mode='json')
    assert activity_rows == []


async def test_video_defaults_to_bounded_real_frames_and_keeps_builder_source_range(database, monkeypatch, tmp_path):
    import av
    import numpy as np
    from app.editing.timing import SOURCE_TIMEBASE
    from app.models.schemas import PrepareVideoMaterialsArgs
    from app.pipeline import step_context

    video_path = tmp_path / 'source.mp4'
    with av.open(str(video_path), mode='w') as container:
        stream = container.add_stream('mpeg4', rate=30)
        stream.width, stream.height = 64, 32
        stream.pix_fmt = 'yuv420p'
        for index in range(60):
            pixels = np.full((32, 64, 3), index * 4, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format='rgb24')
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)

    async with database() as db:
        user = User(email=f'{uuid4()}@test.local')
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title='video frames')
        db.add(project)
        await db.flush()
        asset = Asset(
            user_id=user.id, project_id=project.id, type=AssetType.VIDEO,
            processing_status=AssetStatus.COMPLETED, file_url='source.mp4',
        )
        db.add(asset)
        await db.commit()
        uid, pid, aid = user.id, project.id, asset.id

    async def freeze(db, asset, *, owner_id):
        snapshot = SourceSnapshot(
            owner_id=owner_id, asset_id=asset.id, kind='video',
            storage_key=asset.file_url, digest='c' * 64,
            duration_ticks=2 * SOURCE_TIMEBASE,
            meta={'width': 64, 'height': 32},
        )
        db.add(snapshot)
        await db.flush()
        return snapshot

    async def local_file(_key):
        return video_path

    monkeypatch.setattr(design, 'AsyncSessionLocal', database)
    monkeypatch.setattr(design, 'snapshot_video_asset', freeze)
    monkeypatch.setattr(step_context, 'download_to_temp', local_file)
    facts, images = await design.prepare_video_materials(
        owner_id=uid, project_id=pid,
        args=PrepareVideoMaterialsArgs(material_asset_ids=[aid]),
    )
    assert len(images) == 3
    assert all(image.type == 'image' and image.mime == 'image/jpeg' for image in images)
    assert all('not continuous playback' in image.caption for image in images)
    resource = facts['resources'][0]
    assert resource['model_evidence']['mode'] == 'representative_frames'
    assert resource['model_evidence']['continuous_review'] is False
    assert len(resource['model_evidence']['frames']) == 3
    assert resource['clip_source'] == {
        'snapshot_id': resource['snapshot_id'],
        'snapshot_digest': 'c' * 64,
        'source_range': {'start': 0, 'end': 2 * SOURCE_TIMEBASE},
    }
    assert resource['width'] == 64 and resource['height'] == 32
    assert facts['media_omitted'] == []


async def test_resumed_loop_restores_prior_draft_but_owns_new_exchanges(monkeypatch):
    import json
    from app.chat.conversation_context import ConversationContext

    turn_id = uuid4()
    draft_id = 'current-draft'
    digest = 'a' * 64
    prior = {
        'id': f'{turn_id}:0:0:design', 'turn_id': str(turn_id),
        'tool': 'design_video', 'arguments': {},
        'executed_arguments': {'content': {'scenes': []}},
        'text': json.dumps({'draft_id': draft_id, 'draft_digest': digest}),
        'ok': True, 'media_refs': [], 'resource_keys': [],
        'candidate': {'candidate_id': draft_id, 'candidate_digest': digest,
                      'target_tool': 'design_video', 'active': True},
    }
    records = [prior]

    async def load():
        return records, {str(turn_id): 'Make a video'}, 120000

    async def media(items):
        return (), []

    context = ConversationContext(
        conversation_id=uuid4(), owner_id=uuid4(), turn_id=turn_id, resume_turn=True,
    )
    monkeypatch.setattr(context, '_load', load)
    monkeypatch.setattr(context, '_media', media)
    history = await context.restore(None, [])
    assert len(history.candidates) == 1
    assert history.candidates[0].candidate_id == draft_id
    assert history.candidates[0].candidate_digest == digest
    records.append({**prior, 'id': f'{turn_id}:1:0:lookup', 'tool': 'get_asset',
                    'text': 'new loop result', 'candidate': None})
    history = await context.restore(None, [])
    assert len(history.candidates) == 1
    assert 'new loop result' not in str(history.messages)

    ordinary = ConversationContext(conversation_id=uuid4(), owner_id=uuid4(), turn_id=turn_id)
    monkeypatch.setattr(ordinary, '_load', load)
    monkeypatch.setattr(ordinary, '_media', media)
    assert not (await ordinary.restore(None, [])).candidates
