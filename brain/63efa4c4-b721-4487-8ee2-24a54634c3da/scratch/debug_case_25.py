from cases.models import Case
from users.models import User
try:
    c = Case.objects.get(id=25)
    d = getattr(c, 'deceased', None)
    print(f'Case: {c}')
    print(f'Deceased Name: {d.name if d else "None"}')
    heirs = c.heirs.all()
    print(f'Linked Heirs: {list(heirs)}')
    
    if d and d.name:
        pending_users = User.objects.filter(
            role=User.Role.HEIR, 
            deceased_name__icontains=d.name,
            heir_records__isnull=True
        )
        print(f'Pending Heirs Count: {pending_users.count()}')
        for u in pending_users:
            print(f' - User ID: {u.id}, Name: {u.full_name}, Deceased Claim: {u.deceased_name}')
    else:
        print('No deceased name to match against.')
except Exception as e:
    print(f'Error: {e}')
