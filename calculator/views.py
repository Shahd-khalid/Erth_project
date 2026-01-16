from django.shortcuts import render
from .engine import InheritanceEngine
from cases.models import Heir
from decimal import Decimal

def public_calculator(request):
    result = None
    error = None
    
    if request.method == 'POST':
        try:
            net_estate = Decimal(request.POST.get('net_estate', 0))
            
            # Construct heirs list from form data
            # This is a simplified manual construction for the public calculator
            heirs_data = []
            
            # Helper to add heirs
            def add_heir(rel, gender, count=1):
                for i in range(int(count)):
                    heirs_data.append(Heir(
                        id=len(heirs_data)+1, 
                        name=f"{rel} {i+1}", 
                        relationship=rel, 
                        gender=gender
                    ))

            if request.POST.get('husband'): add_heir(Heir.Relationship.HUSBAND, Heir.Gender.MALE)
            if request.POST.get('wife'): add_heir(Heir.Relationship.WIFE, Heir.Gender.FEMALE)
            if request.POST.get('father'): add_heir(Heir.Relationship.FATHER, Heir.Gender.MALE)
            if request.POST.get('mother'): add_heir(Heir.Relationship.MOTHER, Heir.Gender.FEMALE)
            
            sons = request.POST.get('sons', 0)
            if sons: add_heir(Heir.Relationship.SON, Heir.Gender.MALE, sons)
            
            daughters = request.POST.get('daughters', 0)
            if daughters: add_heir(Heir.Relationship.DAUGHTER, Heir.Gender.FEMALE, daughters)
            
            brothers = request.POST.get('brothers', 0)
            if brothers: add_heir(Heir.Relationship.BROTHER, Heir.Gender.MALE, brothers)
            
            if request.POST.get('sisters'): add_heir(Heir.Relationship.SISTER, Heir.Gender.FEMALE, request.POST.get('sisters'))

            # --- Grandparents ---
            if request.POST.get('grandfathers_father'): add_heir(Heir.Relationship.GRANDFATHER_FATHER, Heir.Gender.MALE, request.POST.get('grandfathers_father'))
            if request.POST.get('grandmothers_father'): add_heir(Heir.Relationship.GRANDMOTHER_FATHER, Heir.Gender.FEMALE, request.POST.get('grandmothers_father'))
            if request.POST.get('grandmothers_mother'): add_heir(Heir.Relationship.GRANDMOTHER_MOTHER, Heir.Gender.FEMALE, request.POST.get('grandmothers_mother'))

            # --- Grandchildren ---
            if request.POST.get('son_of_son'): add_heir(Heir.Relationship.SON_OF_SON, Heir.Gender.MALE, request.POST.get('son_of_son'))
            if request.POST.get('daughter_of_son'): add_heir(Heir.Relationship.DAUGHTER_OF_SON, Heir.Gender.FEMALE, request.POST.get('daughter_of_son'))

            # --- Paternal/Maternal Siblings ---
            if request.POST.get('brothers_father'): add_heir(Heir.Relationship.BROTHER_FATHER, Heir.Gender.MALE, request.POST.get('brothers_father'))
            if request.POST.get('sisters_father'): add_heir(Heir.Relationship.SISTER_FATHER, Heir.Gender.FEMALE, request.POST.get('sisters_father'))
            if request.POST.get('brothers_mother'): add_heir(Heir.Relationship.BROTHER_MOTHER, Heir.Gender.MALE, request.POST.get('brothers_mother'))
            if request.POST.get('sisters_mother'): add_heir(Heir.Relationship.SISTER_MOTHER, Heir.Gender.FEMALE, request.POST.get('sisters_mother'))

            # --- Nephews ---
            if request.POST.get('son_of_brother'): add_heir(Heir.Relationship.SON_OF_BROTHER, Heir.Gender.MALE, request.POST.get('son_of_brother'))
            if request.POST.get('son_of_brother_father'): add_heir(Heir.Relationship.SON_OF_BROTHER_FATHER, Heir.Gender.MALE, request.POST.get('son_of_brother_father'))

            # --- Uncles ---
            if request.POST.get('uncles'): add_heir(Heir.Relationship.UNCLE, Heir.Gender.MALE, request.POST.get('uncles'))
            if request.POST.get('uncles_father'): add_heir(Heir.Relationship.UNCLE_FATHER, Heir.Gender.MALE, request.POST.get('uncles_father'))

            # --- Cousins ---
            if request.POST.get('son_of_uncle'): add_heir(Heir.Relationship.SON_OF_UNCLE, Heir.Gender.MALE, request.POST.get('son_of_uncle'))
            if request.POST.get('son_of_uncle_father'): add_heir(Heir.Relationship.SON_OF_UNCLE_FATHER, Heir.Gender.MALE, request.POST.get('son_of_uncle_father'))

            engine = InheritanceEngine(net_estate, heirs_data)
            shares = engine.calculate()
            
            # Format result for template
            result = []
            for heir_id, data in shares.items():
                heir = next(h for h in heirs_data if h.id == heir_id)
                result.append({
                    'name': heir.name,
                    'relationship': heir.get_relationship_display(),
                    'fraction': data['fraction'],
                    'value': data['value']
                })
                
        except Exception as e:
            error = f"حدث خطأ في الحساب: {str(e)}"

    return render(request, 'calculator/public_calculator.html', {'result': result, 'error': error})
    