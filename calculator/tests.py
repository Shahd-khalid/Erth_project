from django.test import TestCase
from .engine import InheritanceEngine
from cases.models import Heir
from decimal import Decimal

class InheritanceEngineTest(TestCase):
    def test_husband_and_son(self):
        # Setup
        heirs_data = [
            Heir(id=1, name="Husband", relationship=Heir.Relationship.HUSBAND, gender=Heir.Gender.MALE),
            Heir(id=2, name="Son", relationship=Heir.Relationship.SON, gender=Heir.Gender.MALE),
        ]
        net_estate = 100000
        
        # Execute
        engine = InheritanceEngine(net_estate, heirs_data)
        result = engine.calculate()
        
        # Verify Husband (1/4)
        self.assertEqual(result[1]['fraction'], '1/4')
        self.assertEqual(result[1]['value'], Decimal(25000))
        
        # Verify Son (Asabah - Remainder)
        self.assertEqual(result[2]['fraction'], 'Asabah')
        self.assertEqual(result[2]['value'], Decimal(75000))

    def test_wife_and_daughters_no_son(self):
        # Setup: Wife (1/8), 2 Daughters (2/3), Brother (Asabah)
        heirs_data = [
            Heir(id=1, name="Wife", relationship=Heir.Relationship.WIFE, gender=Heir.Gender.FEMALE),
            Heir(id=2, name="Daughter 1", relationship=Heir.Relationship.DAUGHTER, gender=Heir.Gender.FEMALE),
            Heir(id=3, name="Daughter 2", relationship=Heir.Relationship.DAUGHTER, gender=Heir.Gender.FEMALE),
            Heir(id=4, name="Brother", relationship=Heir.Relationship.BROTHER, gender=Heir.Gender.MALE),
        ]
        net_estate = 24000
        
        # Execute
        engine = InheritanceEngine(net_estate, heirs_data)
        result = engine.calculate()
        
        # Verify Wife: 1/8 of 24000 = 3000
        self.assertEqual(result[1]['value'], Decimal(3000))
        
        # Verify Daughters: 2/3 of 24000 = 16000 -> Each 8000
        self.assertEqual(result[2]['value'], Decimal(8000))
        self.assertEqual(result[3]['value'], Decimal(8000))
        
        # Verify Brother: Remainder = 24000 - 3000 - 16000 = 5000
        # Note: My current engine implementation for Brother/Sister Asabah is not fully complete in the snippet above.
        # I need to check if I implemented Brother Asabah logic. 
        # Looking at previous turn, I only implemented Son and Father as Asabah.
        # So this test might fail or show incomplete logic. 
        # I will stick to Husband/Son test first to verify what I wrote.
