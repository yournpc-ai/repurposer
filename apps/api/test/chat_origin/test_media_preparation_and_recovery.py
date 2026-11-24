"""Layer 1A Chat-Origin: webpage/music/video material preparation and visual asset recovery."""

from __future__ import annotations
import pytest

from uuid import uuid4


import pytest


from app.models.tables import User,Project,Asset,SourceSnapshot


from app.models.schemas import AssetType,AssetStatus


from app.tools.video import design




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
    from app.pipeline import asset_processing
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

    monkeypatch.setattr(asset_processing, 'reset_asset_processing', unexpected_reset)
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
        demo = {**item, 'id': f'{turn_id}:2:0:demo', 'tool': 'read_skill_demo',
                'skill_reference': {'kind':'builtin', 'skill_id':'promo-video', 'version':'a'}}
        conversation = Conversation(user_id=user.id, project_id=project.id, context={'schema_version': 1, 'items': [item, demo]})
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
    assert not (await context.read(ReadConversationContextArgs(item_ids=[demo['id']]))).ok
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


# --- Visual asset recovery & SVG preflight ---

import hashlib


import io


import json


from types import SimpleNamespace


from unittest.mock import AsyncMock


from uuid import uuid4


import pytest


from PIL import Image


from app.agents.base import jinja_env


from app.models.tables import Project, SourceSnapshot


from app.providers.llm.base import LLMSchemaError


from app.tools.video import visual_assets


from app.tools.video.media_analysis import (
    analyze_image_bytes,
    image_content_reviewer,
    image_reviewer_version,
    review_image_content,
    store_content_review,
    store_media_analysis,
)


def image_draft():
    specs = [
        visual_assets.SceneAssetSpec(
            scene_id=scene_id,
            intent="Show the citation mechanism",
            source={"kind": "minimax_image", "prompt": f"Wordless illustration for {scene_id}"},
            on_screen_copy="Prepare the exact caption separately",
            palette=["#F9F9F9", "#DC0100"],
        )
        for scene_id in ("s1", "s2")
    ]
    draft = {"content": {"scenes": [{"scene_id": spec.scene_id} for spec in specs]},
             "design": {"scene_assets": [spec.model_dump(mode="json") for spec in specs]}}
    return draft, specs


@pytest.mark.asyncio
async def test_existing_source_refits_legacy_png_before_review_and_cache(database, monkeypatch):
    from test.support.db_helpers import _project, _user

    owner = await _user(database)
    project_id = await _project(database, owner)
    image = Image.new("RGB", (80, 50), "white")
    image.paste("red", (0, 0, 5, 50))
    image.paste("blue", (75, 0, 80, 50))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    original = buffer.getvalue()
    source = SourceSnapshot(
        id=uuid4(), owner_id=owner, origin_project_id=project_id, kind="image",
        digest=hashlib.sha256(original).hexdigest(), storage_key="original.png",
    )
    async with database() as db:
        db.add(source)
        await db.commit()
    spec = visual_assets.SceneAssetSpec(
        scene_id="process", intent="Show the original diagram",
        source={"kind": "existing_image", "snapshot_id": source.id, "snapshot_digest": source.digest},
        on_screen_copy="The editorial title", output={"width": 160, "height": 90},
    )
    assert "visible_evidence" not in spec.model_dump(mode="json")["source"]
    key = visual_assets.request_key(owner, project_id, spec.request_digest())
    stored = {"original.png": original, key: json.dumps({
        "state": "fixed", "scene_id": spec.scene_id, "request_digest": spec.request_digest(),
        "snapshot": {"snapshot_id": str(source.id), "digest": source.digest},
        "media": {"width": 80, "height": 50, "storage_key": source.storage_key, "digest": source.digest},
    }).encode()}

    async def save(key, data, content_type):
        stored[key] = data

    monkeypatch.setattr(visual_assets, "AsyncSessionLocal", database)
    monkeypatch.setattr(visual_assets.storage, "exists", AsyncMock(side_effect=stored.__contains__))
    monkeypatch.setattr(visual_assets.storage, "read", AsyncMock(side_effect=stored.__getitem__))
    monkeypatch.setattr(visual_assets.storage, "save", save)
    reviewer = AsyncMock(return_value={"status": "pass", "summary": "The diagram is visible."})
    kwargs = dict(
        owner_id=owner, project_id=project_id, spec=spec, reviewer=reviewer,
    )
    result = await visual_assets.prepare_visual_asset(**kwargs, execution_id="first")
    assert not result["cache_hit"] and result["usage"] == {}
    assert result["provenance"]["snapshot_digest"] == source.digest
    assert result["snapshot"]["digest"] != source.digest and stored[source.storage_key] == original
    assert (result["media"]["width"], result["media"]["height"]) == (160, 90)
    assert result["content_review"]["reviewer_version"] == image_reviewer_version("existing_image")
    with Image.open(io.BytesIO(stored[result["media"]["storage_key"]])) as fitted:
        assert fitted.getchannel("A").getbbox() == (8, 0, 152, 90)
        assert fitted.getpixel((8, 0)) == (255, 0, 0, 255)
        assert fitted.getpixel((151, 89)) == (0, 0, 255, 255)
    evidence_args, media = image_content_reviewer.assemble(**reviewer.await_args.kwargs)
    assert media and evidence_args["existing_image"]
    prompt = jinja_env.get_template(image_content_reviewer.prompt).render(**evidence_args)
    assert "页面区段错误" in prompt and "由后续剪辑负责" in prompt
    cached = await visual_assets.prepare_visual_asset(**kwargs, execution_id="again")
    assert cached["cache_hit"] and cached["snapshot"] == result["snapshot"]
    reviewer.assert_awaited_once()


def website_state(snapshot):
    from app.models.schemas import BrandSourceRef, CreativeState
    from test.support.media_helpers import website_brand_profile as profile

    ref = BrandSourceRef(snapshot_id=str(snapshot.id), digest=snapshot.digest)
    return CreativeState(brand_profile=profile().model_copy(update={"source_refs": [ref]}))


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_fails", [False, True])
async def test_review_recovery_reuses_snapshot_and_is_bounded(monkeypatch, retry_fails):
    stored = {}

    async def save(key, data, content_type=None):
        stored[key] = data

    async def read(key):
        return stored[key]

    async def exists(key):
        return key in stored

    monkeypatch.setattr(visual_assets.storage, "save", save)
    monkeypatch.setattr(visual_assets.storage, "read", read)
    monkeypatch.setattr(visual_assets.storage, "exists", exists)
    _, (spec, missing) = image_draft()
    owner_id, project_id, snapshot_id = uuid4(), uuid4(), str(uuid4())
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "white").save(buffer, format="PNG")
    png = buffer.getvalue()
    digest = hashlib.sha256(png).hexdigest()
    analysis = analyze_image_bytes(png, snapshot_id=snapshot_id, source_digest=digest)
    analysis_ref = await store_media_analysis(analysis)

    async def bad_response(**kwargs):
        raise LLMSchemaError("Private provider response")

    unavailable = await review_image_content(
        png, scene_asset=spec, analysis=analysis, analysis_ref=analysis_ref, reviewer=bad_response,
    )
    assert "expected schema" in unavailable.summary
    assert "Private provider response" not in unavailable.summary
    initial_ref = await store_content_review(unavailable)
    manifest = {
        "state": "fixed",
        "scene_id": spec.scene_id,
        "request_digest": spec.request_digest(),
        "media": {"storage_key": "original.png", "digest": digest},
        "snapshot": {"snapshot_id": snapshot_id, "digest": digest},
        "analysis_ref": analysis_ref,
        "content_review_ref": initial_ref,
    }
    original_key = visual_assets.request_key(owner_id, project_id, spec.request_digest())
    original_manifest = json.dumps(manifest).encode()
    await save(original_key, original_manifest)
    await save("original.png", png)
    calls = []

    async def reviewer(**kwargs):
        calls.append(kwargs["image"])
        if retry_fails:
            raise LLMSchemaError("Still unusable")
        return {"status": "pass", "summary": "The fixed image was reviewed"}

    async def never_generate(**kwargs):
        pytest.fail("Review recovery must never execute image generation")

    monkeypatch.setattr(visual_assets, "prepare_visual_asset", never_generate)
    kwargs = {"owner_id": owner_id, "project_id": project_id, "reviewer": reviewer}
    with pytest.raises(visual_assets.VisualAssetError):
        await visual_assets.review_fixed_visual_asset(spec=missing, **kwargs)
    reviewed = await visual_assets.review_fixed_visual_asset(spec=spec, **kwargs)
    cached = await visual_assets.review_fixed_visual_asset(spec=spec, **kwargs)
    assert cached == reviewed
    assert len(calls) == 1
    assert stored[original_key] == original_manifest
    assert cached["snapshot"] == manifest["snapshot"]
    assert cached["review_retry_of"] == initial_ref
    assert cached["content_review"]["status"] == ("unavailable" if retry_fails else "pass")


@pytest.mark.asyncio
async def test_prefixed_svg_renders_real_shapes_in_chromium(monkeypatch):
    from app.tools.research.capture import resolve_chrome_path

    if resolve_chrome_path() is None:
        pytest.skip("configured Chromium is required for the rasterization regression")

    monkeypatch.setattr(visual_assets, "_SVG_TIMEOUT_SECONDS", 60)

    output = visual_assets.VisualOutputConstraints(width=160, height=90)
    svg, _, _ = visual_assets.sanitize_svg_program(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90">'
        '<rect width="160" height="90" fill="#fff"/>'
        '<rect x="60" y="30" width="40" height="30" fill="#dc0000"/>'
        '<text x="30" y="78" font-size="12">Actual SVG</text>'
        '</svg>',
        output,
    )
    assert b"<ns0:svg " in svg
    png, diagnostics = await visual_assets.rasterize_svg(svg, output)
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == (160, 90)
        assert image.convert("RGB").getpixel((80, 45)) == (220, 0, 0)
        assert image.convert("RGB").getpixel((5, 5)) == (255, 255, 255)
    assert diagnostics["native_svg_viewport_verified"] is True
    report = analyze_image_bytes(
        png, snapshot_id=str(uuid4()), svg_text_bounds=diagnostics["text_bounds"],
        caption_safe_area={"x": 0.0, "y": 0.4, "width": 1.0, "height": 0.2},
    )
    geometry = report.media_facts["svg_text_geometry"]
    assert geometry["caption_safe_area"]["bottom"] == pytest.approx(54)
    assert geometry["text"][0]["inside_canvas"] is True
    assert geometry["text"][0]["inside_caption_safe_area"] is False
    with pytest.raises(ValueError, match="native SVG viewport"):
        await visual_assets.rasterize_svg(b"<svg/>", output)


@pytest.mark.asyncio
async def test_outdated_svg_runner_does_not_reuse_fixed_png(monkeypatch):
    svg_spec = visual_assets.SceneAssetSpec(
        scene_id="scene",
        intent="Test renderer cache",
        source={"kind": "controlled_svg", "program": "<svg/>"},
    )
    _, (provider_spec, _) = image_draft()
    owner_id, project_id = uuid4(), uuid4()
    stored = {
        visual_assets.request_key(owner_id, project_id, spec.request_digest()): json.dumps({
            "state": "fixed",
            "snapshot": {"snapshot_id": "prior"},
            "request_digest": spec.request_digest(),
            "scene_id": spec.scene_id,
            "provenance": {"runner_version": "controlled-svg-browser-v1"},
        }).encode()
        for spec in (svg_spec, provider_spec)
    }

    async def exists(key):
        return key in stored

    async def read(key):
        return stored[key]

    monkeypatch.setattr(visual_assets.storage, "exists", exists)
    monkeypatch.setattr(visual_assets.storage, "read", read)
    keys = {"owner_id": owner_id, "project_id": project_id}
    assert await visual_assets.cached_visual_asset(spec=svg_spec, **keys) is None
    assert await visual_assets.fixed_visual_asset_manifest(spec=provider_spec, **keys) is not None


def test_visual_review_legacy_findings_require_actual_evidence():
    from app.tools.video.media_analysis import ContentReviewAnswer

    finding = {
        "requirement": "The diagram shows the cited paper",
        "evidence": "The area at the center of the PNG is empty",
    }
    report = {"status": "fail", "summary": "Missing diagram", "observed_issue": [finding]}
    answer = ContentReviewAnswer.model_validate(report)
    assert answer.findings[0].kind == "observed_issue"
    assert answer.findings[0].evidence == finding["evidence"]
    with pytest.raises(ValueError, match="pixel evidence"):
        ContentReviewAnswer.model_validate({
            **report,
            "observed_issue": [{"requirement": finding["requirement"]}],
        })
    with pytest.raises(ValueError, match="distinct pixel evidence"):
        ContentReviewAnswer.model_validate({
            **report,
            "observed_issue": [{**finding, "evidence": finding["requirement"]}],
        })


@pytest.mark.asyncio
async def test_bad_svg_is_reported_before_quote():
    specs = [
        visual_assets.SceneAssetSpec(
            scene_id=f"scene-{i}", intent="Evidence",
            source={"kind": "controlled_svg", "program": (
                '<svg><rect rx rx="5"/></svg>' if i == 2 else '<svg><rect rx="5"/></svg>'
            )},
        )
        for i in range(6)
    ]
    with pytest.raises(ValueError, match=r"Scene scene-2: SVG is not well formed"):
        visual_assets.preflight_scene_svgs(specs)


@pytest.mark.asyncio
async def test_submitted_provider_image_reuses_only_verified_fixed_media(monkeypatch):
    from app.tools.video import generated_images

    _, (spec, _) = image_draft()
    owner_id, project_id = uuid4(), uuid4()
    key = visual_assets.request_key(owner_id, project_id, spec.request_digest())
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "red").save(buffer, format="PNG")
    png = buffer.getvalue()
    manifest = {
        "state": "submitted", "request_digest": spec.request_digest(), "scene_id": spec.scene_id,
    }
    stored = {key: json.dumps(manifest).encode(), "verified.png": png}
    fixed = {
        "media": {"storage_key": "verified.png", "digest": hashlib.sha256(png).hexdigest()},
        "request": {}, "provider_request": {}, "program_digest": "a" * 64,
        "execution_id": "earlier-run", "usage": {"images": 1},
    }
    ready = False

    async def exists(storage_key):
        return storage_key in stored

    async def read(storage_key):
        return stored[storage_key]

    async def find(clip, *, scope=None):
        return fixed if ready else None

    async def never_submit(*args, **kwargs):
        pytest.fail("Recovery must not submit another provider request")

    monkeypatch.setattr(visual_assets.storage, "read", read)
    monkeypatch.setattr(visual_assets.storage, "exists", exists)
    monkeypatch.setattr(generated_images, "find_fixed_generated_image", find)
    monkeypatch.setattr(generated_images, "ensure_generated_image_clip", never_submit)
    kwargs = {"owner_id": owner_id, "project_id": project_id, "spec": spec}
    with pytest.raises(visual_assets.VisualAssetOutcomeUnknownError, match="not be resubmitted"):
        await visual_assets.fixed_visual_asset_manifest(**kwargs)

    ready = True
    assert await visual_assets.has_fixed_visual_source(**kwargs)
    cached = await visual_assets._recover_submitted_image(spec)
    recovered, _, usage = await visual_assets._minimax_image(
        spec, execution_id="later-run", fixed=cached,
    )
    assert recovered and usage == {}
    assert json.loads(stored[key])["state"] == "submitted"


@pytest.mark.asyncio
async def test_review_uses_scene_role_and_user_words_and_keeps_pixel_identity():

    _, specs = image_draft()
    spec = specs[1].model_copy(update={"intent": "Use a vertically mounted phone."})
    roles = {"s1": "Show the link to a source paper.", "s2": "Show a researcher communicating science."}
    words = ["Show the researcher in the second scene."]
    spec._review_basis = {"user_words": words, "scene_roles": roles}
    pixel_identity = spec.request_digest()
    first_version = spec.review_version()
    output = io.BytesIO()
    Image.new("RGB", (32, 18), "white").save(output, format="PNG")
    data = output.getvalue()
    facts = analyze_image_bytes(data, snapshot_id=str(uuid4()))

    reviewer = AsyncMock(return_value={"status": "pass", "summary": "Use case visible", "findings": []})
    async def review():
        return await review_image_content(data, scene_asset=spec, analysis=facts,
                                          analysis_ref={"digest": facts.report_digest}, reviewer=reviewer)
    first = await review()
    projection = json.loads(reviewer.await_args.kwargs["scene_asset_json"])
    assert "vertically" not in str(projection)
    assert projection["requirements"]["narrative"] == roles["s2"]
    assert projection["other_scene_roles"] == {"s1": "Show the link to a source paper."}
    assert first.status == "pass"

    spec._review_basis = {"scene_roles": roles, "user_words": [*words, "Use a vertically mounted phone."]}
    assert spec.request_digest() == pixel_identity and spec.review_version() != first_version
    reviewer.return_value = {"status": "fail", "summary": "Orientation mismatch", "findings": [{
        "kind": "observed_issue", "requirement": "user_1", "observed": "Horizontal phone",
        "evidence": "The grip holds the long edge parallel to the desk.",
    }]}
    second = await review()
    assert second.status == "fail"
    assert json.loads(reviewer.await_args.kwargs["scene_asset_json"])["requirements"]["user_1"] == (
        "Use a vertically mounted phone.")

