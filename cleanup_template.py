import re

file_path = r'c:\Users\PC\Desktop\mawareth_project\templates\cases\allocate_share.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern to find the stray tags after the first endif of is_heir_process
# Look for {% endif %} followed by stray tags ending before allocation-section-grid
pattern = re.compile(r'\{% endif %\}\s+</div>\s+{% else %}\s+<div class="allocation-empty">.*?{% endif %}\s+</div>\s+</div>\s+<div class="allocation-section-grid', re.DOTALL)

new_content = pattern.sub('{% endif %}\n\n                <div class="allocation-section-grid', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Cleanup successful.")
