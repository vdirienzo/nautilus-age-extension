# 🚀 GUÍA RÁPIDA DE INSTALACIÓN - AGE NAUTILUS

## ⚡ Instalación en 3 pasos

### 1️⃣ Descarga los archivos
Ya los tienes! Simplemente extrae el ZIP o clona el repo.

### 2️⃣ Ejecuta el instalador
```bash
cd age-nautilus-extension
chmod +x install-age-nautilus.sh
./install-age-nautilus.sh
```

### 3️⃣ ¡Listo!
Abre Nautilus y click derecho en cualquier archivo. Verás las nuevas opciones de encriptación.

---

## 🎯 Uso básico

### Encriptar un archivo
1. Click derecho en el archivo
2. Selecciona "🔒 Encrypt with age"
3. Ingresa contraseña (2 veces)
4. Listo! Se crea `archivo.ext.age`

### Desencriptar un archivo
1. Click derecho en `archivo.ext.age`
2. Selecciona "🔓 Decrypt with age"
3. Ingresa contraseña
4. Listo! Se recupera `archivo.ext`

### Encriptar una carpeta completa
1. Click derecho en la carpeta
2. Selecciona "📦 Encrypt folder with age"
3. Ingresa contraseña
4. Listo! Se crea `carpeta.tar.gz.age`

---

## 🛠️ Verificación

Para verificar que todo está instalado correctamente:
```bash
./test-age-nautilus.sh
```

---

## ❓ ¿Problemas?

### La extensión no aparece
```bash
nautilus -q
killall nautilus
nautilus &
```

### Falta alguna dependencia
```bash
sudo apt install python3-nautilus age zenity libnotify-bin
```

---

## 📚 Más información

Lee el **README.md** completo para:
- Todas las características
- Ejemplos avanzados
- Troubleshooting detallado
- Configuración avanzada

---

## 🗑️ Desinstalar

```bash
./uninstall-age-nautilus.sh
```

---

**¡Disfruta de la encriptación segura con age! 🔐**

Para cualquier duda, abre un issue en GitHub o revisa la documentación completa.
