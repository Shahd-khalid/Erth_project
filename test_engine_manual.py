import sys
import os
from decimal import Decimal

# Mock Heir and Relationship
class MockHeir:
    class Relationship:
        HUSBAND = 'HUSBAND'
        WIFE = 'WIFE'
        SON = 'SON'
        DAUGHTER = 'DAUGHTER'
        FATHER = 'FATHER'
        MOTHER = 'MOTHER'
        BROTHER = 'BROTHER'
        SISTER = 'SISTER'
        SON_OF_SON = 'SON_OF_SON'
        DAUGHTER_OF_SON = 'DAUGHTER_OF_SON'
        GRANDFATHER_FATHER = 'GRANDFATHER_FATHER'
        GRANDMOTHER_FATHER = 'GRANDMOTHER_FATHER'
        GRANDMOTHER_MOTHER = 'GRANDMOTHER_MOTHER'
        BROTHER_FATHER = 'BROTHER_FATHER'
        SISTER_FATHER = 'SISTER_FATHER'
        BROTHER_MOTHER = 'BROTHER_MOTHER'
        SISTER_MOTHER = 'SISTER_MOTHER'
        SON_OF_BROTHER = 'SON_OF_BROTHER'
        SON_OF_BROTHER_FATHER = 'SON_OF_BROTHER_FATHER'
        UNCLE = 'UNCLE'
        UNCLE_FATHER = 'UNCLE_FATHER'
        SON_OF_UNCLE = 'SON_OF_UNCLE'
        SON_OF_UNCLE_FATHER = 'SON_OF_UNCLE_FATHER'

    def __init__(self, id, relationship, is_blocked=False):
        self.id = id
        self.relationship = relationship
        self.is_blocked = is_blocked
        self.name = relationship

# Patch sys.modules to allow importing engine without Django
# We need to mock 'cases.models' before importing calculator.engine
from unittest.mock import MagicMock
sys.modules['cases.models'] = MagicMock()
sys.modules['cases.models'].Heir = MockHeir

# Now import the engine (assuming it's in the current path or we add it)
# Since I am writing this to the root or a temp place, I need to point to the file I just wrote.
# I will copy the engine code briefly here or simpler: I will assume I can import it if I set pythonpath.
# Actually, since I have view_file capability, I know the content. 
# Best approach: Write a script that INCLUDES the engine code or imports it from the file system.
# Given the file is at .../calculator/engine.py, I can add that dir to sys.path.

sys.path.append(r"c:\Users\PC\Downloads\mawareth_project _الجلسة\mawareth_project")
from calculator.engine import InheritanceEngine

def run_test(name, net_estate, heirs, expected_checks):
    print(f"--- Running Test: {name} ---")
    engine = InheritanceEngine(net_estate, heirs)
    result = engine.calculate()
    
    for heir in heirs:
        res = result.get(heir.id)
        if not res and not heir.is_blocked:
             # It might be blocked by engine
             if heir in engine.blocked_heirs:
                 print(f"Heir {heir.relationship} BLOCKED (Correct? Check logic)")
             else:
                 print(f"Heir {heir.relationship} MISSING in result!")
             continue
        
        if res:
            print(f"{heir.relationship}: {res['fraction']} -> {res['value']}")

            # Simple Verification Checks
            if heir.id in expected_checks:
                exp = expected_checks[heir.id]
                val = res['value']
                if abs(val - Decimal(exp)) > Decimal(1):
                    print(f"  [FAIL] Expected {exp}, got {val}")
                else:
                    print(f"  [PASS] Value matches approximately")

# Case 1: Son blocks Brother
heirs1 = [
    MockHeir(1, MockHeir.Relationship.SON),
    MockHeir(2, MockHeir.Relationship.BROTHER)
]
run_test("Hajb - Son blocks Brother", 1000, heirs1, {1: 1000, 2: 0})

# Case 2: Husband + Daughter
heirs2 = [
    MockHeir(1, MockHeir.Relationship.HUSBAND),
    MockHeir(2, MockHeir.Relationship.DAUGHTER)
]
# Husband 1/4 = 250. Daughter 1/2 = 500. Total 750. Remainder 250.
# Radd: Remainder returned to Daughter (Husband excluded from Radd).
# Daughter Total = 500 + 250 = 750.
# Husband = 250.
run_test("Faraid + Radd - Husband & Daughter", 1000, heirs2, {1: 250, 2: 750})

# Case 3: Son + Daughter
heirs3 = [
    MockHeir(1, MockHeir.Relationship.SON),
    MockHeir(2, MockHeir.Relationship.DAUGHTER)
]
# Ratio 2:1. Total 3 units.
# Son 2/3 = 666.67. Daughter 1/3 = 333.33
run_test("Ta'sib - Son & Daughter", 1000, heirs3, {1: 666.67, 2: 333.33})

# Case 4: Father + Mother + Son
heirs4 = [
    MockHeir(1, MockHeir.Relationship.FATHER),
    MockHeir(2, MockHeir.Relationship.MOTHER),
    MockHeir(3, MockHeir.Relationship.SON)
]
# Father 1/6 (due to male desc) = 166.67
# Mother 1/6 (due to desc) = 166.67
# Son Remainder (Asabah) = 1 - 1/3 = 2/3 = 666.67
run_test("Mixed - Father, Mother, Son", 1000, heirs4, {1: 166.67, 2: 166.67, 3: 666.67})

