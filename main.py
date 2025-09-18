import pandas as pd
import os

# Ruta del archivo CSV
CSV_PATH = "output/data.csv"

def crear_dataframe_inicial():
    data = {
        "Nombre": ["Ana", "Luis", "María"],
        "Edad": [28, 34, 25],
        "Ciudad": ["Madrid", "Barcelona", "Valencia"]
    }
    df = pd.DataFrame(data)
    return df

def guardar_csv(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    print(f"✅ CSV guardado en: {path}")

def leer_csv(path):
    df = pd.read_csv(path)
    print(f"📄 CSV leído desde: {path}")
    return df

def añadir_fila(df):
    nueva_fila = {"Nombre": "New Insert", "Edad": 30, "Ciudad": "Sevilla"}
    df = pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)
    return df

def main():
    # SECRET AREA
    secret = "empty"
    print(f"El secret antes de acceder a el es: {secret}")
    
    secret = os.getenv("SECRET_TEST")

    if secret != 'empty':
         print("✅ El secret fue cargado correctamente.")
    
    if secret == 'madness':
        print("✅ El contenido del secret fue cargado correctamente.")
        print(f"El secret despues de acceder a el es: {secret}")
    else:
        print("❌ El contenido del secret no es correcto.")

    # CSV AREA
    print("🔧 Creando DataFrame inicial...")
    df = crear_dataframe_inicial()
    guardar_csv(df, CSV_PATH)

    print("📥 Leyendo CSV...")
    df_leido = leer_csv(CSV_PATH)

    print("➕ Añadiendo nueva fila...")
    df_modificado = añadir_fila(df_leido)

    print("💾 Guardando CSV actualizado...")
    guardar_csv(df_modificado, CSV_PATH)

if __name__ == "__main__":
    main()
