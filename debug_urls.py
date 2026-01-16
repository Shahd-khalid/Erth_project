import os
import django
from django.urls import reverse, resolve

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mawareth_project.settings')
django.setup()

def check_url():
    try:
        url = reverse('judges:clerk_list')
        print(f"Success! URL for 'judges:clerk_list' is: {url}")
        
        match = resolve(url)
        print(f"Resolved View: {match.func.__name__}")
        print(f"App Name: {match.app_name}")
        print(f"Namespace: {match.namespace}")
        
    except Exception as e:
        print(f"Error reversing URL: {e}")
        
        # List all urls to help debug
        from django.urls import get_resolver
        resolver = get_resolver()
        print("\nListing all registered URLs under 'judges' namespace:")
        try:
            judges_patterns = resolver.resolve_error_handler.url_patterns if hasattr(resolver, 'resolve_error_handler') else []
            # This is complex to walk, let's just use the known structure
            pass
        except:
            pass
            
if __name__ == "__main__":
    check_url()
