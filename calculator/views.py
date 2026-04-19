from decimal import Decimal

from django.shortcuts import render

from cases.models import Heir

from .engine import InheritanceEngine


def _process_public_calculation(request):
    result = []
    chart_data = None
    error = None
    net_estate = Decimal(0)

    try:
        net_estate = Decimal(request.POST.get("net_estate", 0))

        # Construct heirs list from form data for the public calculator.
        heirs_data = []

        def add_heir(rel, gender, count=1):
            for i in range(int(count)):
                heirs_data.append(
                    Heir(
                        id=len(heirs_data) + 1,
                        name=f"{rel} {i + 1}",
                        relationship=rel,
                        gender=gender,
                    )
                )

        if request.POST.get("husband"): add_heir(Heir.Relationship.HUSBAND, Heir.Gender.MALE)
        if request.POST.get("wife"): add_heir(Heir.Relationship.WIFE, Heir.Gender.FEMALE)
        if request.POST.get("father"): add_heir(Heir.Relationship.FATHER, Heir.Gender.MALE)
        if request.POST.get("mother"): add_heir(Heir.Relationship.MOTHER, Heir.Gender.FEMALE)

        sons = request.POST.get("sons", 0)
        if sons: add_heir(Heir.Relationship.SON, Heir.Gender.MALE, sons)
        
        daughters = request.POST.get("daughters", 0)
        if daughters: add_heir(Heir.Relationship.DAUGHTER, Heir.Gender.FEMALE, daughters)

        brothers = request.POST.get("brothers", 0)
        if brothers: add_heir(Heir.Relationship.BROTHER, Heir.Gender.MALE, brothers)

        if request.POST.get("sisters"):
            add_heir(Heir.Relationship.SISTER, Heir.Gender.FEMALE, request.POST.get("sisters"))

        if request.POST.get("grandfathers_father"):
            add_heir(Heir.Relationship.GRANDFATHER_FATHER, Heir.Gender.MALE, request.POST.get("grandfathers_father"))
        
        if request.POST.get("grandmothers_father"):
            add_heir(Heir.Relationship.GRANDMOTHER_FATHER, Heir.Gender.FEMALE, request.POST.get("grandmothers_father"))
        
        if request.POST.get("grandmothers_mother"):
            add_heir(Heir.Relationship.GRANDMOTHER_MOTHER, Heir.Gender.FEMALE, request.POST.get("grandmothers_mother"))

        if request.POST.get("son_of_son"):
            add_heir(Heir.Relationship.SON_OF_SON, Heir.Gender.MALE, request.POST.get("son_of_son"))
        
        if request.POST.get("daughter_of_son"):
            add_heir(Heir.Relationship.DAUGHTER_OF_SON, Heir.Gender.FEMALE, request.POST.get("daughter_of_son"))

        if request.POST.get("brothers_father"):
            add_heir(Heir.Relationship.BROTHER_FATHER, Heir.Gender.MALE, request.POST.get("brothers_father"))
        
        if request.POST.get("sisters_father"):
            add_heir(Heir.Relationship.SISTER_FATHER, Heir.Gender.FEMALE, request.POST.get("sisters_father"))
        
        if request.POST.get("brothers_mother"):
            add_heir(Heir.Relationship.BROTHER_MOTHER, Heir.Gender.MALE, request.POST.get("brothers_mother"))
        
        if request.POST.get("sisters_mother"):
            add_heir(Heir.Relationship.SISTER_MOTHER, Heir.Gender.FEMALE, request.POST.get("sisters_mother"))

        if request.POST.get("son_of_brother"):
            add_heir(Heir.Relationship.SON_OF_BROTHER, Heir.Gender.MALE, request.POST.get("son_of_brother"))
        
        if request.POST.get("son_of_brother_father"):
            add_heir(Heir.Relationship.SON_OF_BROTHER_FATHER, Heir.Gender.MALE, request.POST.get("son_of_brother_father"))

        if request.POST.get("uncles"):
            add_heir(Heir.Relationship.UNCLE, Heir.Gender.MALE, request.POST.get("uncles"))
        
        if request.POST.get("uncles_father"):
            add_heir(Heir.Relationship.UNCLE_FATHER, Heir.Gender.MALE, request.POST.get("uncles_father"))

        if request.POST.get("son_of_uncle"):
            add_heir(Heir.Relationship.SON_OF_UNCLE, Heir.Gender.MALE, request.POST.get("son_of_uncle"))
        
        if request.POST.get("son_of_uncle_father"):
            add_heir(Heir.Relationship.SON_OF_UNCLE_FATHER, Heir.Gender.MALE, request.POST.get("son_of_uncle_father"))

        engine = InheritanceEngine(net_estate, heirs_data)
        shares = engine.calculate()

        chart_labels = []
        chart_values = []
        relationship_counts = {}

        for heir_id, data in shares.items():
            heir = next(h for h in heirs_data if h.id == heir_id)
            relationship_label = heir.get_relationship_display()
            relationship_counts.setdefault(relationship_label, 0)
            relationship_counts[relationship_label] += 1

            display_name = relationship_label
            if relationship_counts[relationship_label] > 1:
                display_name = f"{relationship_label} {relationship_counts[relationship_label]}"

            heir_value = data.get("value", 0) or 0

            result.append(
                {
                    "name": display_name,
                    "relationship": relationship_label,
                    "fraction": data["fraction"],
                    "value": heir_value,
                    "blocking_reason": data.get("blocking_reason", ""),
                    "adjustment": data.get("adjustment", ""),
                }
            )

            if heir_value > 0:
                chart_labels.append(display_name)
                chart_values.append(float(heir_value))

        if chart_labels and any(value > 0 for value in chart_values):
            chart_data = {
                "labels": chart_labels,
                "values": chart_values,
            }

    except Exception as e:
        error = f"حدث خطأ في الحساب: {str(e)}"

    return result, chart_data, error, net_estate

def public_calculator(request):
    """عشر عرض الحاسبة العامة"""
    return render(request, "calculator/public_calculator.html")

def public_calculator_results(request):
    """عرض صفحة نتائج الحساب في صفحة جديدة"""
    if request.method != "POST":
        return redirect('calculator:public_calculator')
        
    result, chart_data, error, net_estate = _process_public_calculation(request)
    
    return render(
        request,
        "calculator/public_calculator_results.html",
        {
            "result": result,
            "error": error,
            "chart_data": chart_data,
            "net_estate": net_estate,
        },
    )

