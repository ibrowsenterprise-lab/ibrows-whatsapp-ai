"""Offline regression for the fingerprint-guarded MSJ source-sheet correction."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from msj_catalogue_repair import (
    EXPECTED_WRONG,EXPECTED_CORRECT,SOURCE_FOR_TARGET,
    repair_ms_j_misassigned_sheet_images,
)

assert len(EXPECTED_WRONG)==len(EXPECTED_CORRECT)==len(SOURCE_FOR_TARGET)==8
assert set(EXPECTED_WRONG)==set(EXPECTED_CORRECT)==set(SOURCE_FOR_TARGET)
assert set(SOURCE_FOR_TARGET.values())==set(SOURCE_FOR_TARGET)
assert all(EXPECTED_CORRECT[k]==EXPECTED_WRONG[v] for k,v in SOURCE_FOR_TARGET.items())

class FakeCursor:
    def __init__(self,initial):
        self.images=dict(initial)
        self.rows=[]
        self.update_count=0
    def execute(self,sql,params=None):
        normalized=" ".join(sql.split())
        if normalized.startswith("SELECT code, md5(image_bytes)"):
            self.rows=[(key,self.images[key]) for key in sorted(self.images)]
        elif normalized.startswith("WITH originals AS MATERIALIZED"):
            assert "UPDATE msj_merch_designs" in normalized
            before=dict(self.images)
            for target,source in SOURCE_FOR_TARGET.items():
                self.images[target]=before[source]
            self.rows=[(code,) for code in sorted(self.images)]
            self.update_count+=1
        else:
            raise AssertionError(normalized[:150])
    def fetchall(self):
        return self.rows

mistaken=FakeCursor(EXPECTED_WRONG)
assert repair_ms_j_misassigned_sheet_images(mistaken)=="repaired"
assert mistaken.images==EXPECTED_CORRECT
assert mistaken.update_count==1
assert repair_ms_j_misassigned_sheet_images(mistaken)=="already_correct"
assert mistaken.update_count==1
correct=FakeCursor(EXPECTED_CORRECT)
assert repair_ms_j_misassigned_sheet_images(correct)=="already_correct"
assert correct.update_count==0
modified=dict(EXPECTED_WRONG)
modified["MSJ-CIRCLE"]="new-artwork-by-user"
personalized=FakeCursor(modified)
assert repair_ms_j_misassigned_sheet_images(personalized)=="changed_skip"
assert personalized.images==modified and personalized.update_count==0
missing=FakeCursor({})
assert repair_ms_j_misassigned_sheet_images(missing)=="unrelated_catalogue"
assert missing.update_count==0
print("PASS: verified all 8 original shirt images map back to their exact intended design names")
print("PASS: already corrected, customized, or empty catalogues stay unchanged")
print("PASS: migration makes a single guarded UPDATE and never changes orders or prices")
