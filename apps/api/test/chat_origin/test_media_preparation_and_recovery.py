"""Library music preparation and reuse across Studio chats."""
from uuid import uuid4

import pytest

from app.agents import tool_progress
from app.models.tables import Project, User
from app.tools.video import design
from test.support.chat_http import tool_result

pytestmark = pytest.mark.chat_origin


async def test_real_music_bytes_freeze_once_and_reuse_across_owned_chats(database,monkeypatch):
    import io

    import av
    from sqlalchemy import select

    from app.models.schemas import PrepareVideoMaterialsArgs
    from app.models.tables import Music, SourceSnapshot
    from app.tools.video import preparation
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
    from app.agents.tool_progress import ToolProgress, current_call_id
    steps = []
    report = tool_progress.report_progress

    async def progress(step):
        steps.append(ToolProgress(current_call_id(), step))
        await report(step)

    monkeypatch.setattr(tool_progress, "report_progress", progress)

    async def prepare(pid):
        result, _ = await tool_result(database, monkeypatch, uid, pid, "Prepare this music for my film.",
            "prepare_video_materials", args.model_dump(mode="json"), call_id="import",
            operation="app.tools.video.design.prepare_video_materials")
        return result[0]

    first = await prepare(pa)
    assert steps == [ToolProgress("import", "import_music")]
    repeated = await prepare(pa)
    other = await prepare(pb)
    ids=[r['resources'][0]['snapshot_id'] for r in (first,repeated,other)]
    assert ids[0]==ids[1]==ids[2]
    async with database() as db:
        row=await db.scalar(select(SourceSnapshot).where(SourceSnapshot.owner_id==uid))
        assert row.origin_project_id==pa and row.kind=='audio' and row.duration_ticks>0
        assert row.meta['music']['music_id']==str(mid)
        assert objects[row.storage_key]==audio
