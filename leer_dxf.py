import ezdxf

# Ruta del archivo DXF
archivo_dxf = "planos/mi_plano.dxf"

# Abrimos el archivo DXF
doc = ezdxf.readfile(archivo_dxf)

# Accedemos al modelo (donde están las entidades)
msp = doc.modelspace()

print("Entidades encontradas en el DXF:")

# Recorremos entidades y mostramos información básica
for entity in msp:
    print(f"Tipo: {entity.dxftype()}")
    
    if entity.dxftype() == 'LINE':
        start = entity.dxf.start
        end = entity.dxf.end
        length = ((end[0] - start[0])**2 + (end[1] - start[1])**2) ** 0.5
        print(f"  Línea desde {start} hasta {end} - Longitud: {length:.2f}")

