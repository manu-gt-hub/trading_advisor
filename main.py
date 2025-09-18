import pandas as pd
import os

CSV_PATH = "data/data.csv"

def cargar_o_crear_dataframe():
    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        print("✅ CSV cargado.")
    else:
        df = pd.DataFrame(columns=["Nombre", "Edad", "Ciudad"])
        print("📄 CSV no encontrado. Creando uno nuevo.")
    return df

def añadir_fila(df):
    nueva_fila = {"Nombre": "Carlos", "Edad": 30, "Ciudad": "Sevilla"}
    return pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)

def guardar_dataframe(df):
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    print(f"💾 CSV guardado en {CSV_PATH}")

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
    df = cargar_o_crear_dataframe()
    
    print("➕ Añadiendo nueva fila...")
    df = añadir_fila(df)

    print("💾 Guardando CSV actualizado...")
    guardar_dataframe(df)


if __name__ == "__main__":
    main()
