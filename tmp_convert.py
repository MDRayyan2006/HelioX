import re
import os

html_path = r"c:\helioLasthope\.stitch\designs\react_bits.html"
out_dir = r"c:\helioLasthope\ui\src\features\react-bits\components"
out_path = os.path.join(out_dir, "ReactBitsScreen.tsx")

os.makedirs(out_dir, exist_ok=True)

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

# Extract the body contents 
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
body_html = body_match.group(1) if body_match else html

# Easy conversions for JSX
body_html = body_html.replace('class=', 'className=')
body_html = body_html.replace('for=', 'htmlFor=')
body_html = body_html.replace('style=""', '')
# Self closing tags
body_html = re.sub(r'(<img[^>]*?)(?<!/)>', r'\1 />', body_html)
body_html = re.sub(r'(<input[^>]*?)(?<!/)>', r'\1 />', body_html)

tsx_content = f"""import React from 'react';

// Converted from Stitch MCP HTML Generation
export const ReactBitsScreen: React.FC = () => {{
  return (
    <div className="bg-[#131314] text-[#e5e2e3] font-['Plus_Jakarta_Sans'] min-h-screen">
      {{/* Original Body Content */}}
      {body_html}
    </div>
  );
}};

export default ReactBitsScreen;
"""

with open(out_path, "w", encoding="utf-8") as f:
    f.write(tsx_content)

print(f"Successfully converted ReactBitsScreen.tsx to {out_path}")
