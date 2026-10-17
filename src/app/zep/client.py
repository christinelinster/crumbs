"""Construct the managed Zep SDK client."""
from zep_cloud import Zep

from app import settings


def get_zep():
    return Zep(api_key=settings.ZEP_API_KEY)
