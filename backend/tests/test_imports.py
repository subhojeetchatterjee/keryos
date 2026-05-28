import pytest


def test_import_tools_modules():
    from agents.tools import retry
    from agents.tools import api_cache
    from agents.tools import env_config
    from agents.tools import stats_utils
    from agents.tools import geojson_utils
    from agents.tools import cdse_auth
    from agents.tools import sentinelhub_catalog
    from agents.tools import sentinelhub_process
    from agents.tools import sentinelhub_stats
    from agents.tools import best_images
    from agents.tools import report_bundle

    assert retry is not None
    assert api_cache is not None
    assert env_config is not None
    assert stats_utils is not None
    assert geojson_utils is not None
    assert cdse_auth is not None
    assert sentinelhub_catalog is not None
    assert sentinelhub_process is not None
    assert sentinelhub_stats is not None
    assert best_images is not None
    assert report_bundle is not None


def test_import_utils_modules():
    from utils import messages
    from utils import pdf_generator

    assert messages is not None
    assert pdf_generator is not None


def test_import_streamlit_app():
    import streamlit_app

    assert streamlit_app is not None
