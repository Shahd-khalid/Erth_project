from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def dashboard(request):
    if request.user.role == 'JUDGE':
        return redirect('judges:dashboard')
    elif request.user.role == 'CLERK':
        return redirect('clerks:dashboard')
    elif request.user.role == 'HEIR':
        return redirect('heirs:dashboard')
    elif request.user.role == 'ADMIN':
        return redirect('administration:dashboard')
    return render(request, 'dashboard/public_dashboard.html')
