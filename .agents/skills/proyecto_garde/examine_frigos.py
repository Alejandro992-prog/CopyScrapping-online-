import json

with open(r"c:\Users\aleja\OneDrive\Escritorio\Programacion programas etc\ideas Nuevos Proyectos\CopyScrapping (online)\data\stock\inventory.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total productos en inventario: {len(data)}")

categories = {}
brands = {}
colors = {}

for p in data:
    cat = p.get("category", "Otros")
    categories[cat] = categories.get(cat, 0) + 1
    
    br = p.get("brand", "Genérico")
    brands[br] = brands.get(br, 0) + 1
    
    col = p.get("color", "")
    if col:
        colors[col] = colors.get(col, 0) + 1

print("\n--- Categorías ---")
for k, v in sorted(categories.items(), key=lambda x: x[1], reverse=True):
    print(f"  {k}: {v} productos")

print("\n--- Colores ---")
for k, v in sorted(colors.items(), key=lambda x: x[1], reverse=True):
    print(f"  {k}: {v} productos")

