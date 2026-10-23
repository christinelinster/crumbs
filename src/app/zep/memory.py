"""Opt-in conversation writes and ownership checks for the shared Zep user."""
from zep_cloud import AddMessage

from app import settings
from app.zep.client import get_zep


class ThreadOwnershipError(ValueError):
    pass


def prepare_thread(thread_uuid):
    if not settings.ZEP_USER_UUID:
        raise RuntimeError('Set ZEP_USER_UUID to enable shared memory')
    client = get_zep()
    if thread_uuid:
        thread_uuid = str(thread_uuid)
        if client.thread.get(thread_uuid).user_uuid != settings.ZEP_USER_UUID:
            raise ThreadOwnershipError('shared test thread not found')
    else:
        thread_uuid = client.thread.create(user_uuid=settings.ZEP_USER_UUID).uuid_
    return client, thread_uuid


def save_messages(client, thread_uuid, question, answer):
    return client.thread.add_messages(
        thread_uuid,
        messages=[AddMessage(role='user', content=question), AddMessage(role='assistant', content=answer)],
        ignore_roles=['assistant'],
    )
