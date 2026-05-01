import os
import re

def get_all_imports(directory):
    imports = set()
    from_imports = set()
    
    # Regex to catch 'import module' and 'from module import ...'
    import_re = re.compile(r'^\s*import\s+([a-zA-Z0-9_]+)', re.MULTILINE)
    from_re = re.compile(r'^\s*from\s+([a-zA-Z0-9_]+)', re.MULTILINE)

    for root, dirs, files in os.walk(directory):
        if 'venv' in root or '.git' in root or '.gemini' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        content = f.read()
                        for match in import_re.findall(content):
                            imports.add(match)
                        for match in from_re.findall(content):
                            from_imports.add(match)
                except Exception:
                    pass
    
    return sorted(list(imports | from_imports))

if __name__ == "__main__":
    all_deps = get_all_imports(".")
    print("\n".join(all_deps))
