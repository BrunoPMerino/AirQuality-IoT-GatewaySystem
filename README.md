# AirQuality IoT Gateway System

Sistema IoT de monitoreo de calidad del aire desarrollado para la región de Sabana Centro, Cundinamarca. El proyecto integra un nodo sensor basado en ESP32, una Raspberry Pi como Gateway IoT, comunicación MQTT, almacenamiento local en SQLite, visualización global en Ubidots e Inteligencia Artificial mediante Gemini API para generar recomendaciones ambientales.

---

## Descripción General

El sistema permite medir variables ambientales en tiempo real, procesarlas mediante una lógica de fusión de datos y generar alertas locales cuando se detectan condiciones de riesgo. Además, los datos son enviados desde el ESP32 hacia una Raspberry Pi mediante MQTT, donde se almacenan localmente, se procesan y se reenvían hacia una plataforma global en Ubidots.

La Raspberry Pi también integra Gemini API para analizar la medición actual junto con el histórico reciente y generar una recomendación ambiental orientada a apoyar la toma de decisiones.

---

## Objetivo del Proyecto

Desarrollar un sistema IoT funcional, de bajo costo y escalable para monitorear la calidad del aire, generar alertas tempranas in situ, almacenar datos localmente y visualizar la información en un dashboard global.

El sistema busca responder a la necesidad de contar con herramientas de monitoreo ambiental distribuido que permitan detectar condiciones críticas en microentornos urbanos o académicos.

---

## Arquitectura del Sistema

La arquitectura está compuesta por tres niveles principales:

1. **Nodo Sensor ESP32**  
   Encargado de leer sensores, calcular la lógica de fusión, activar alertas físicas y publicar datos por MQTT.

2. **Raspberry Pi Gateway**  
   Encargada de recibir los datos del ESP32, almacenarlos en SQLite, consultar Gemini API y reenviar la información hacia Ubidots.

3. **Plataforma Global Ubidots**  
   Encargada de visualizar variables ambientales, histórico reciente, índice de riesgo y recomendaciones generadas por IA.

---

## Video Demostrativo

El funcionamiento completo del sistema puede observarse en el siguiente video:

[Ver video demostrativo del proyecto](https://youtu.be/7Rk_wSKeCNo)
