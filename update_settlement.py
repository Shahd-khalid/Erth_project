import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

from cases.models import PaymentSettlement, Case, Heir

def find_settlement():
    try:
        # البحث في جميع التسويات عن مبلغ 10.00
        settlements = PaymentSettlement.objects.filter(amount=10.00)
        
        if not settlements.exists():
            print("لم يتم العثور على أي تسوية مالية بقيمة 10.00 في أي قضية.")
            return
            
        print("تم العثور على التسويات التالية بقيمة 10.00:")
        for s in settlements:
            payer_name = s.payer.name if s.payer else "لا يوجد"
            print(f"- القضية رقم: {s.case.id} | اسم القضية: {s.case.case_number}")
            print(f"  رقم الوريث: {s.payer.id if s.payer else 'N/A'} | اسم الوريث: {payer_name}")
            print(f"  رقم التسوية: {s.id} | السبب: {s.reason}")
            
            # إذا تبيّن أنها هي التي يقصدها المستخدم، نقوم بتعديلها هنا مباشرة
            if payer_name.strip() == "وريث 3" or payer_name.strip() == "وريث3" or "3" in payer_name:
                print(f"--> جاري تغيير المبلغ إلى 5 لريال التسوية (ID={s.id})...")
                s.amount = 5
                s.save()
                print("--> تمت العملية بنجاح!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_settlement()
