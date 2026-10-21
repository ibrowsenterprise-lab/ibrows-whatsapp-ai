"""Contract tests for the IBROWS-managed agriculture marketplace.

These are intentionally failing until marketplace integration is implemented.
Run against a dedicated TEST database, never the live production DB.
"""
import pytest

@pytest.mark.skip(reason='Marketplace endpoints not implemented yet; requires isolated test database')
def test_pending_listing_never_public():
    assert False

@pytest.mark.skip(reason='Marketplace endpoints not implemented yet; requires isolated test database')
def test_approved_listing_public_without_seller_pii():
    assert False

@pytest.mark.skip(reason='Marketplace endpoints not implemented yet; requires isolated test database')
def test_buyer_enquiry_goes_to_ibrows_not_seller():
    assert False

@pytest.mark.skip(reason='Marketplace endpoints not implemented yet; requires isolated test database')
def test_moderation_requires_admin_and_csrf():
    assert False
