import pytest
from peewee import Model, BlobField, TextField

from slim.retcode import RETCODE
from slim.support.peewee import PeeweeView
from slim.tools.test import invoke_interface, get_app, get_peewee_db

pytestmark = [pytest.mark.asyncio]
app = get_app()
db = get_peewee_db()


class ATestModel(Model):
    name = TextField()

    class Meta:
        table_name = 'test'
        database = db


db.create_tables([ATestModel])


@app.route('test')
class ATestView(PeeweeView):
    model = ATestModel

app._prepare()


async def test_invoke_interface():
    resp = await invoke_interface(app, ATestView.get)
    assert resp.ret_val['code'] == RETCODE.NOT_FOUND

    ATestModel.create(name='Alice')

    resp = await invoke_interface(app, ATestView.get)
    assert resp.ret_val['code'] == RETCODE.SUCCESS
