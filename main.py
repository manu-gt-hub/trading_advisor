import os

def main():
    secret = "empty"
    print(f"El secret antes de acceder a el es: {secret}")
    
    secret = os.getenv("SECRET_TEST")
    
    if secret:
        print("✅ El secret fue cargado correctamente.")
        print(f"El secret despues de acceder a el es: {secret}")
    else:
        print("❌ No se pudo cargar el secret.")

if __name__ == "__main__":
    main()
