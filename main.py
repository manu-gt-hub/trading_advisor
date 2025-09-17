import os

def main():
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

if __name__ == "__main__":
    main()
