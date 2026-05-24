import json
import os
import sqlite3
from datetime import datetime

import paho.mqtt.client as mqtt
from google import genai


# ============================================================
# CONFIGURACIÓN LOCAL
# ============================================================

DB_NAME = "airquality.db"

LOCAL_MQTT_BROKER = "localhost"
LOCAL_MQTT_PORT = 1883
LOCAL_TOPIC = "airquality/esp32/data"


# ============================================================
# CONFIGURACIÓN UBIDOTS
# ============================================================

UBIDOTS_BROKER = "industrial.api.ubidots.com"
UBIDOTS_PORT = 1883
UBIDOTS_DEVICE = "air-quality-gateway"
UBIDOTS_TOPIC = f"/v1.6/devices/{UBIDOTS_DEVICE}"

# Recomendado: cargar desde variable de entorno
# export UBIDOTS_TOKEN="TU_TOKEN_REAL"
UBIDOTS_TOKEN = os.getenv("UBIDOTS_TOKEN", "TU_TOKEN_DE_UBIDOTS")


# ============================================================
# CONFIGURACIÓN GEMINI
# ============================================================

# Recomendado: cargar desde variable de entorno
# export GEMINI_API_KEY="TU_API_KEY_REAL"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"


# ============================================================
# CLIENTE MQTT COMPATIBLE
# ============================================================

def create_mqtt_client():
    """
    Crea un cliente MQTT compatible con versiones nuevas y antiguas de paho-mqtt.
    """
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:
        return mqtt.Client()


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def get_trend_text(trend_code):
    """
    Convierte el código de tendencia en texto.
    """
    if trend_code == 1:
        return "Riesgo subiendo"
    elif trend_code == -1:
        return "Riesgo bajando"
    else:
        return "Riesgo estable"


def get_recommendation_label(recommendation_code):
    """
    Convierte el código de recomendación en texto corto.
    """
    if recommendation_code == 3:
        return "Alerta crítica"
    elif recommendation_code == 2:
        return "Alerta moderada"
    elif recommendation_code == 1:
        return "Monitoreo preventivo"
    else:
        return "Condición normal"


# ============================================================
# BASE DE DATOS SQLITE
# ============================================================

def add_column_if_not_exists(cursor, column_name, column_type):
    """
    Agrega una columna a la tabla measurements si todavía no existe.
    """
    cursor.execute("PRAGMA table_info(measurements)")
    columns = [column[1] for column in cursor.fetchall()]

    if column_name not in columns:
        cursor.execute(f"ALTER TABLE measurements ADD COLUMN {column_name} {column_type}")


def init_database():
    """
    Crea la tabla measurements si no existe.
    También agrega columnas de IA si la tabla ya existía antes.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            pm25 REAL,
            pm10 REAL,
            gas REAL,
            temperature REAL,
            humidity REAL,
            pressure REAL,
            fusion_score REAL,
            risk_level TEXT,
            ai_recommendation TEXT,
            ai_recommendation_code INTEGER,
            ai_trend_code INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    add_column_if_not_exists(cursor, "ai_recommendation", "TEXT")
    add_column_if_not_exists(cursor, "ai_recommendation_code", "INTEGER")
    add_column_if_not_exists(cursor, "ai_trend_code", "INTEGER")

    conn.commit()
    conn.close()


def save_to_database(data, ai_result):
    """
    Guarda la medición recibida desde el ESP32 junto con el resultado de Gemini.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO measurements (
            device_id,
            pm25,
            pm10,
            gas,
            temperature,
            humidity,
            pressure,
            fusion_score,
            risk_level,
            ai_recommendation,
            ai_recommendation_code,
            ai_trend_code,
            timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("device_id", "ESP32_AIR_001"),
        data.get("pm25"),
        data.get("pm10"),
        data.get("gas"),
        data.get("temperature"),
        data.get("humidity"),
        data.get("pressure"),
        data.get("fusion_score"),
        data.get("risk_level", "UNKNOWN"),
        ai_result.get("recommendation_text"),
        ai_result.get("recommendation_code"),
        ai_result.get("trend_code"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def get_recent_measurements(limit=6):
    """
    Obtiene las últimas mediciones para que Gemini pueda analizar tendencia.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pm25,
            pm10,
            gas,
            temperature,
            humidity,
            pressure,
            fusion_score,
            risk_level,
            timestamp
        FROM measurements
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    rows.reverse()

    recent_data = []
    for row in rows:
        recent_data.append({
            "pm25": row[0],
            "pm10": row[1],
            "gas": row[2],
            "temperature": row[3],
            "humidity": row[4],
            "pressure": row[5],
            "fusion_score": row[6],
            "risk_level": row[7],
            "timestamp": row[8]
        })

    return recent_data


# ============================================================
# RESPALDO LOCAL SI GEMINI FALLA
# ============================================================

def local_ai_fallback(data):
    """
    Recomendación local de respaldo si Gemini falla o no hay API Key.
    """
    fusion_score = float(data.get("fusion_score", 0))
    pm25 = float(data.get("pm25", 0))
    humidity = float(data.get("humidity", 0))

    if fusion_score >= 80 or pm25 >= 70:
        recommendation_text = (
            "Alerta crítica: evitar exposición al aire libre, revisar fuentes "
            "de contaminación y mantener activas las alertas."
        )
        recommendation_code = 3
        trend_code = 1

    elif fusion_score >= 60 or pm25 >= 35:
        recommendation_text = (
            "Alerta moderada: mantener monitoreo continuo y reducir actividades "
            "al aire libre para población vulnerable."
        )
        recommendation_code = 2
        trend_code = 0

    elif fusion_score >= 40:
        recommendation_text = (
            "Monitoreo preventivo: las condiciones requieren seguimiento, "
            "aunque todavía no representan una condición crítica."
        )
        recommendation_code = 1
        trend_code = 0

    else:
        recommendation_text = (
            "Condición normal: los valores actuales se mantienen en un rango aceptable."
        )
        recommendation_code = 0
        trend_code = 0

    if humidity >= 75 and recommendation_code >= 2:
        recommendation_text += " Humedad elevada: vigilar posible acumulación de contaminantes."

    return {
        "recommendation_text": recommendation_text,
        "recommendation_code": recommendation_code,
        "trend_code": trend_code
    }


# ============================================================
# MÓDULO IA CON GEMINI
# ============================================================

def run_gemini_ai_module(data):
    """
    Envía los datos actuales e históricos a Gemini.
    Gemini devuelve:
    - recommendation_text
    - recommendation_code
    - trend_code
    """

    if not GEMINI_API_KEY:
        print("Advertencia: GEMINI_API_KEY no está configurada. Usando respaldo local.")
        return local_ai_fallback(data)

    recent_data = get_recent_measurements(limit=6)

    prompt = f"""
Eres un asistente técnico para un sistema IoT de monitoreo de calidad del aire
en Sabana Centro, Cundinamarca.

Analiza la medición actual y el histórico reciente. Genera una recomendación
breve, clara y útil para autoridades locales.

Datos actuales:
- PM2.5: {data.get("pm25")}
- PM10: {data.get("pm10")}
- Gas MQ135 crudo: {data.get("gas")}
- Temperatura: {data.get("temperature")} °C
- Humedad: {data.get("humidity")} %
- Presión: {data.get("pressure")} hPa
- Fusion score: {data.get("fusion_score")} sobre 100
- Nivel de riesgo calculado por ESP32: {data.get("risk_level")}

Histórico reciente:
{json.dumps(recent_data, ensure_ascii=False)}

Debes responder ÚNICAMENTE en JSON válido.
No uses markdown.
No uses comillas triples.
No agregues explicación adicional.

Formato obligatorio:
{{
  "recommendation_text": "Texto breve de máximo 35 palabras.",
  "recommendation_code": 0,
  "trend_code": 0
}}

Criterios:
- recommendation_code:
  0 = condición normal
  1 = monitoreo preventivo
  2 = alerta moderada
  3 = alerta crítica

- trend_code:
  -1 = riesgo bajando
  0 = riesgo estable
  1 = riesgo subiendo

Usa el fusion_score como señal principal.
También considera PM2.5, PM10, gas, humedad, temperatura y tendencia reciente.
"""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        raw_text = response.text.strip()

        # Limpieza por si Gemini responde accidentalmente en bloque markdown
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        ai_result = json.loads(raw_text)

        recommendation_text = str(
            ai_result.get("recommendation_text", "Sin recomendación generada.")
        )

        recommendation_code = int(ai_result.get("recommendation_code", 0))
        trend_code = int(ai_result.get("trend_code", 0))

        # Protección por si Gemini devuelve valores fuera de rango
        if recommendation_code < 0:
            recommendation_code = 0
        if recommendation_code > 3:
            recommendation_code = 3

        if trend_code not in [-1, 0, 1]:
            trend_code = 0

        return {
            "recommendation_text": recommendation_text,
            "recommendation_code": recommendation_code,
            "trend_code": trend_code
        }

    except Exception as e:
        print("Error consultando Gemini. Usando respaldo local.")
        print("Detalle:", e)
        return local_ai_fallback(data)


# ============================================================
# ENVÍO A UBIDOTS
# ============================================================

def send_to_ubidots(data, ai_result):
    """
    Envía los datos a Ubidots por MQTT.
    Incluye texto de Gemini dentro del context de ai_recommendation_code.
    """

    if UBIDOTS_TOKEN == "TU_TOKEN_DE_UBIDOTS":
        print("ERROR: Debes configurar el token real de Ubidots.")
        print("Usa: export UBIDOTS_TOKEN=\"TU_TOKEN_REAL\"")
        return

    try:
        recommendation_code = int(ai_result.get("recommendation_code", 0))
        trend_code = int(ai_result.get("trend_code", 0))

        recommendation_text = ai_result.get("recommendation_text", "")
        trend_text = get_trend_text(trend_code)
        recommendation_label = get_recommendation_label(recommendation_code)

        ubidots_client = create_mqtt_client()
        ubidots_client.username_pw_set(UBIDOTS_TOKEN, "")

        ubidots_client.connect(UBIDOTS_BROKER, UBIDOTS_PORT, 60)
        ubidots_client.loop_start()

        payload = {
            "pm25": float(data.get("pm25", 0)),
            "pm10": float(data.get("pm10", 0)),
            "gas": float(data.get("gas", 0)),
            "temperature": float(data.get("temperature", 0)),
            "humidity": float(data.get("humidity", 0)),
            "pressure": float(data.get("pressure", 0)),
            "fusion_score": float(data.get("fusion_score", 0)),

            "ai_recommendation_code": {
                "value": recommendation_code,
                "context": {
                    "recommendation_text": recommendation_text,
                    "recommendation_label": recommendation_label,
                    "trend_text": trend_text,
                    "source": "Gemini API"
                }
            },

            "ai_trend_code": {
                "value": trend_code,
                "context": {
                    "trend_text": trend_text,
                    "source": "Gemini API"
                }
            }
        }

        result = ubidots_client.publish(
            UBIDOTS_TOPIC,
            json.dumps(payload),
            qos=1
        )

        result.wait_for_publish()

        print("Resultado publish Ubidots:", result.rc)
        print("Datos enviados a Ubidots:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        ubidots_client.loop_stop()
        ubidots_client.disconnect()

    except Exception as e:
        print("Error enviando datos a Ubidots:", e)


# ============================================================
# CALLBACKS MQTT LOCAL
# ============================================================

def on_connect(client, userdata, flags, rc):
    """
    Se ejecuta cuando la Raspberry se conecta al broker MQTT local.
    """
    if rc == 0:
        print("Conectado al broker MQTT local")
        client.subscribe(LOCAL_TOPIC)
        print("Suscrito al tópico:", LOCAL_TOPIC)
    else:
        print("Error conectando al broker MQTT local. Código:", rc)


def on_message(client, userdata, msg):
    """
    Se ejecuta cada vez que llega un mensaje MQTT desde el ESP32.
    """
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)

        print("\nMensaje recibido desde ESP32:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        ai_result = run_gemini_ai_module(data)

        print("Resultado IA Gemini:")
        print("Recomendación:", ai_result["recommendation_text"])
        print("Código recomendación:", ai_result["recommendation_code"])
        print("Código tendencia:", ai_result["trend_code"])

        save_to_database(data, ai_result)
        print("Datos guardados en SQLite")

        send_to_ubidots(data, ai_result)

    except json.JSONDecodeError:
        print("Error: el mensaje recibido no es un JSON válido")
        print("Payload recibido:", msg.payload.decode())

    except Exception as e:
        print("Error procesando mensaje:", e)


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():
    init_database()

    local_client = create_mqtt_client()
    local_client.on_connect = on_connect
    local_client.on_message = on_message

    print("Iniciando Gateway IoT en Raspberry Pi con Gemini API...")
    print("Broker local:", LOCAL_MQTT_BROKER)
    print("Tópico local:", LOCAL_TOPIC)
    print("Dispositivo Ubidots:", UBIDOTS_DEVICE)
    print("Modelo Gemini:", GEMINI_MODEL)

    local_client.connect(LOCAL_MQTT_BROKER, LOCAL_MQTT_PORT, 60)
    local_client.loop_forever()


if __name__ == "__main__":
    main()