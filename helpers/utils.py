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
