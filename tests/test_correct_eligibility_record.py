"""Offline guards for the one existing paid eligibility customer's service label."""
import unittest
from decimal import Decimal
from correct_eligibility_record import (
    should_relabel_verified_eligibility, TARGET_LEAD_ID, PRICE, NEW_SERVICE,
)

LEAD = (
    19, "Martha", "Scholarship Search",
    "Customer selected the Eligibility Check package (MK5,000) for a Master's scholarship search.",
    None, "MWK", "NEW", "NOT_STARTED", None, None, None
)
PAYMENT = (1,Decimal("5000"),True,True)

class EligibilityRecordTests(unittest.TestCase):
    def test_exact_verified_record_eligible_for_scope_correction(self):
        self.assertTrue(should_relabel_verified_eligibility(LEAD,PAYMENT))
        self.assertEqual(NEW_SERVICE,"Scholarship Eligibility Check")
        self.assertEqual(PRICE,Decimal("5000"))

    def test_never_relabel_other_customers_or_wrong_scope(self):
        for idx,bad in [
            (0,18),(1,"Jones"),(2,"Career Assist"),
            (3,"Selected monthly Scholarship Assist MK60,000"),
            (4,Decimal("5000")),(5,"USD"),(6,"CLOSED"),(7,"ACCEPTED"),
            (8,5),(9,"deleted"),(10,"consumed"),
        ]:
            row=list(LEAD);row[idx]=bad
            with self.subTest(column=idx):
                self.assertFalse(should_relabel_verified_eligibility(tuple(row),PAYMENT))

    def test_no_changes_without_exact_one_verified_payment(self):
        for pay in [
            (0,Decimal("0"),None,None),
            (1,Decimal("2000"),True,True),
            (2,Decimal("5000"),True,True),
            (1,Decimal("5000"),False,True),
            (1,Decimal("5000"),True,False),
            (1,Decimal("6000"),True,True),
        ]:
            with self.subTest(payment=pay):
                self.assertFalse(should_relabel_verified_eligibility(LEAD,pay))

    def test_empty_inputs_cannot_mutate(self):
        self.assertFalse(should_relabel_verified_eligibility(None,PAYMENT))
        self.assertFalse(should_relabel_verified_eligibility(LEAD,None))

if __name__=="__main__": unittest.main()
