# TITAN-MY23- MANUAL-SERVICIO-ES.pdf


================================================================================
PAGE 1
================================================================================

# TITAN SERIES 

## Manual de Servicio

2023

================================================================================
PAGE 2
================================================================================

# CONTENIDO 

## PARTE 1 INFORMACIÓN GENERAL

1. Nombres de Modelos de Unidades Interiores/Exteriores
1.1 Unidades Interiores
1.2 Unidades Exteriores
2.Apariencia Externa
2.1 Unidades Interiores
2.2 Unidades Exteriores
2. Características

## PARTE 2 RESOLUCIÓN DE PROBLEMAS

1.Autodiagnóstico
2.Pasos de Solución para Mal Funcionamiento Típico

================================================================================
PAGE 3
================================================================================

# Parte 1 Información General 

## 1.Nombres de Modelos de Unidades Interiores/Exteriores

### 1.1 Unidades Interiores

| Solo enfriamiento |  |  |  |  |
| :--: | :--: | :--: | :--: | :--: |
| Tipo de unidad interior | Modelo de unidad interior | Capacidad (Btu/h) | Capacidad(k) | Suministro de energía |
| Piso Techo | ATI-PTC3618 | 36000 | 10551 | 220V 50/60Hz 1Ph |
|  | ATI-PTC6018 | 55000 | 16120 | 220V 50/60Hz 1Ph |


| Solo enfriamiento |  |  |  |  |
| :--: | :--: | :--: | :--: | :--: |
| Tipo de unidad interior | Modelo de unidad interior | Capacidad (Btu/h) | Capacidad(k) | Suministro de energía |
| Cassette | ATI-CSC3618 | 36000 | 10551 | 220V 50/60Hz 1Ph |
|  | ATI-CSC6018 | 55000 | 16120 | 220V 50/60Hz 1Ph |

### 1.2 Unidades Exteriores

| Solo enfriamiento |  |  |  |  |
| :--: | :--: | :--: | :--: | :--: |
| Tipo de unidad exterior | Modelo de unidad exterior | Suministro de energía | Modelo de compresor | Marca del compresor |
| Unidad exterior | ATI-CON3618 | 220V/60Hz/1Ph | KTM240D43UMT | GMCC |
|  | ATI-CON6018 | 220V/60Hz/1Ph | GTH420SKPC8DQ | HIGHLY |

================================================================================
PAGE 4
================================================================================

# 2. Apariencia Externa 

### 2.1 Unidades Interiores

Tipo Techo y Piso
![img-0.jpeg](img-0.jpeg)

Tipo Casete
![img-1.jpeg](img-1.jpeg)
2.2 Unidades Exteriores
![img-2.jpeg](img-2.jpeg)

================================================================================
PAGE 5
================================================================================

# 3. Características 

Esta nueva serie de noticias cuenta con las siguientes mejoras y características sobresalientes:

1. Control de conversión de frecuencia, alta eficiencia y ahorro de energía.
2. Aspecto elegante.
3. Eficiencia energética integral estacional de hasta SEER16.
4. Cuerpo compacto con una capacidad de carga más competitiva.
5. Compresores confiables y bien conocidos.
6. Inicio de control RS485 (12V) y 24V, seguro.
7. Válvula de expansión electrónica para lograr un cierre preciso del flujo.
8. Fácil instalación de la unidad.

================================================================================
PAGE 6
================================================================================

# Parte 2 Resolución de Problemas 

## 1. Autodiagnóstico

| Contenido de visualización del LED interior | Definición de falla o protección |
| :--: | :--: |
| Eo | La comunicación entre la unidad interior y exterior es incorrecta. |
| E1 | El Sensor de Temperatura de la Habitación T1 presenta fallas. |
| E2 | El Sensor de Temperatura Interna de la Unidad T2 presenta fallas. |
| E3 | El Sensor de Temperatura Externa T3 presenta fallas. |
| E4 | La unidad exterior tiene errores. |
| E5 | El procesamiento de la configuración del modelo es incorrecto. |
| E6 | El ventilador interior presenta fallas junto con la comunicación entre el DC interior y el panel principal interior. |
| E7 | El Sensor de Temperatura Exterior T4 presenta fallas. |
| E8 | El sensor de temperatura de escape Tp1 de compresor de frecuencia variable es incorrecto. |
| E9 | El módulo de frecuencia variable presenta errores. |
| Ec | La comunicación exterior es incorrecta. |
| EE | EI EEPROM exterior tiene errores (EI E2 de la unidad exterior es incorrecto). |
| EF | El ventilador exterior presenta errores. |
| Ed | EI EEPROM del panel de control principal tiene errores. |
| D3 | Protección por llenado de agua. |
| C5 | La comunicación entre la unidad interior y el controlador por cable es incorrecta. |
| Po | Protección del módulo. |
| P1 | Protección por sobrevoltaje/subvoltaje. |
| P2 | Protección por sobreintensidad (Compresor de frecuencia variable). |
| P3 | Protección de la unidad exterior. |
| P4 | Protección por alta temperatura de escape (Compresor de frecuencia variable o Esclavo F3). |
| P5 | Protección por enfriamiento insuficiente en el modo de enfriamiento (Unidad interior de la bobina). |
| P6 | Protección por sobrecalentamiento en el modo de enfriamiento (Condensador). |
| P7 | Protección por sobrecalentamiento en el modo de calefacción (Unidad interior de la bobina). |
| P8 | Protección por temperatura alta/baja exterior. |
| P9 | Protección por sobrecarga del motor (carga anormal). |
| PA | El modo de operación es conflictivo y la comunicación de parada de aire es incorrecta. |
| F2 | El sensor de temperatura del aire de retorno presenta errores. |
| F3 | Protección por falla del sensor de temperatura de la bobina de la unidad exterior. |

================================================================================
PAGE 7
================================================================================

| H1 | Protección por presostato de alta presión |
| :--: | :-- |
| H2 | Protección por presostato de baja presión |
| Fy | Protección por insuficiencia de refrigerante |

================================================================================
PAGE 8
================================================================================

# 2. Pasos de solución para malfuncionamiento típico 

E0: Falla en la comunicación del bus de las unidades interior y exterior
![img-3.jpeg](img-3.jpeg)

================================================================================
PAGE 9
================================================================================

E1: Falla del sensor de temperatura interior
![img-4.jpeg](img-4.jpeg)

E2: Falla del sensor de temperatura del evaporador
![img-5.jpeg](img-5.jpeg)

================================================================================
PAGE 10
================================================================================

E3: Falla del sensor de temperatura del condensador (enfriamiento y calefacción)
![img-6.jpeg](img-6.jpeg)

E4: Falta de protección del refrigerante
![img-7.jpeg](img-7.jpeg)

================================================================================
PAGE 11
================================================================================

El procesamiento de la configuración del modelo E5 falla.
![img-8.jpeg](img-8.jpeg)

================================================================================
PAGE 12
================================================================================

E7: Falla del sensor de temperatura exterior.
![img-9.jpeg](img-9.jpeg)

E8: Falla del sensor de temperatura de descarga del compresor.
![img-10.jpeg](img-10.jpeg)

================================================================================
PAGE 13
================================================================================

EC: Falla de comunicación del control principal y la unidad exterior.
![img-11.jpeg](img-11.jpeg)

EE: Error en la EEPROM de la placa de control principal de la unidad exterior.
![img-12.jpeg](img-12.jpeg)

================================================================================
PAGE 14
================================================================================

EF: Hay un problema con el ventilador exterior (motor de CC)
![img-13.jpeg](img-13.jpeg)

================================================================================
PAGE 15
================================================================================

d3: Alarma de llenado completo de agua
![img-14.jpeg](img-14.jpeg)

C5: Mala comunicación entre la PCB interior y el controlador de cables (Pantalla del controlador de cables)
![img-15.jpeg](img-15.jpeg)

================================================================================
PAGE 16
================================================================================

P0: Protección del módulo inversor
![img-16.jpeg](img-16.jpeg)

================================================================================
PAGE 17
================================================================================

P7: Protección contra sobrecalentamiento de la calefacción
![img-17.jpeg](img-17.jpeg)

P8: Protección por alta/baja temperatura exterior
![img-18.jpeg](img-18.jpeg)

================================================================================
PAGE 18
================================================================================

H1: Protección por interruptor de alta presión
![img-19.jpeg](img-19.jpeg)

================================================================================
PAGE 19
================================================================================

H2: Protección por interruptor de baja presión
![img-20.jpeg](img-20.jpeg)
