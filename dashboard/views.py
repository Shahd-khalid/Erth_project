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
def simulator(request):
    """
    Publicly accessible visual guide selection.
    """
    return render(request, 'dashboard/visual_guide_selection.html')

def inheritance_tree(request):
    """
    Publicly accessible interactive tree simulator.
    """
    return render(request, 'dashboard/inheritance_tree.html')

def inheritance_table(request):
    """
    Publicly accessible tabular inheritance matrix.
    """
    return render(request, 'dashboard/inheritance_table.html')
def help_page(request):
    """
    Publicly accessible user manual page.
    """
    return render(request, 'dashboard/help.html')
