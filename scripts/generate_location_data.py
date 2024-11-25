import re
import os
from pathlib import Path

def parse_location_data(filename):
    """Parse the location data file and extract provincia/distrito/corregimiento information"""
    print(f"Reading location data from {filename}...")
    
    provincias = {}  # code: name
    distritos = {}   # prov-dist: {name, code, provincia_code}
    corregimientos = []  # list of {name, code, distrito_code}
    
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            # Skip header lines and empty lines
            if not line.strip() or 'Código' in line or 'Ubicación' in line or 'Ficha Técnica' in line:
                continue
                
            # Extract code and full name
            match = re.match(r'(\d+)-(\d+)-(\d+)\s+(.*)', line)
            if not match:
                continue
                
            prov_code, dist_code, corr_code, full_name = match.groups()
            
            # Split location parts
            parts = full_name.split('-')
            if len(parts) != 3:
                continue
                
            provincia, distrito, corregimiento = [p.strip() for p in parts]
            
            # Skip invalid entries
            if 'INVALIDO' in [provincia, distrito, corregimiento]:
                continue
                
            # Store provincia if new
            if prov_code not in provincias:
                provincias[prov_code] = provincia
                print(f"Found new provincia: {provincia} ({prov_code})")
                
            # Store distrito if new
            distrito_key = f"{prov_code}-{dist_code}"
            if distrito_key not in distritos:
                distritos[distrito_key] = {
                    'name': distrito,
                    'code': dist_code,
                    'provincia_code': prov_code
                }
                print(f"Found new distrito: {distrito} ({distrito_key})")
                
            # Store corregimiento
            corregimientos.append({
                'name': corregimiento,
                'code': corr_code,
                'distrito_code': distrito_key
            })
            
    print(f"\nFound {len(provincias)} provincias, {len(distritos)} distritos, and {len(corregimientos)} corregimientos")
    return provincias, distritos, corregimientos

def generate_xml_file(provincias, distritos, corregimientos):
    """Generate the XML file with all location records"""
    
    # Get module root directory (2 levels up from script)
    module_root = Path(__file__).parent.parent
    output_file = module_root / 'data' / 'res_location_pa_data.xml'
    
    print(f"\nGenerating XML file at {output_file}...")
    
    # Create data directory if it doesn't exist
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n    <data noupdate="1">\n')
        
        # Write provincias
        f.write('        <!-- Provincias -->\n')
        for code, name in sorted(provincias.items()):
            f.write(f'''        <record id="provincia_{code}" model="res.provincia.pa">
            <field name="name">{name}</field>
            <field name="code">{code}</field>
        </record>\n\n''')
            
        # Write distritos
        f.write('        <!-- Distritos -->\n')
        for key, dist in sorted(distritos.items()):
            prov_code = dist['provincia_code']
            f.write(f'''        <record id="distrito_{prov_code}_{dist['code']}" model="res.distrito.pa">
            <field name="name">{dist['name']}</field>
            <field name="code">{dist['code']}</field>
            <field name="provincia_id" ref="provincia_{prov_code}"/>
        </record>\n\n''')
            
        # Write corregimientos
        f.write('        <!-- Corregimientos -->\n')
        for corr in sorted(corregimientos, key=lambda x: f"{x['distrito_code']}-{x['code']}"):
            prov_code, dist_code = corr['distrito_code'].split('-')
            f.write(f'''        <record id="corregimiento_{prov_code}_{dist_code}_{corr['code']}" model="res.corregimiento.pa">
            <field name="name">{corr['name']}</field>
            <field name="code">{corr['code']}</field>
            <field name="distrito_id" ref="distrito_{prov_code}_{dist_code}"/>
        </record>\n\n''')
            
        f.write('    </data>\n</odoo>')
    
    print(f"XML file generated successfully at {output_file}")

def main():
    """Main function to generate the location data XML file"""
    script_dir = Path(__file__).parent
    input_file = script_dir / 'location_data.txt'
    
    if not input_file.exists():
        print(f"Error: Input file not found at {input_file}")
        print("Please create location_data.txt with the location data in the scripts directory")
        return
        
    try:
        provincias, distritos, corregimientos = parse_location_data(input_file)
        generate_xml_file(provincias, distritos, corregimientos)
        print("\nProcess completed successfully!")
    except Exception as e:
        print(f"\nError: {str(e)}")

if __name__ == '__main__':
    main()