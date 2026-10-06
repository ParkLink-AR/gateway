# gateway

API Gateway de **ParkLink**: único punto de entrada HTTP para el cliente (app móvil / web).
Enruta cada request al microservicio dueño de ese recurso, valida el JWT emitido por
`auth-service` en el borde, e inyecta la identidad del usuario (`X-User-Id`) para que los
demás servicios no tengan que volver a resolver el token.

Construido con **FastAPI** + **httpx** (proxy HTTP asíncrono) y un cliente de **RabbitMQ**
(`aio-pika`) para la infraestructura de eventos async que ya usa el resto del sistema.

## Por qué HTTP hacia los servicios, y no RabbitMQ

`auth-service`, `parking-service` y `payment-service` ya están construidos como APIs REST.
Convertirlos a request/reply sobre AMQP implicaría meterse en esos tres repos (que mantiene
cada equipo) solo para reemplazar algo que HTTP ya resuelve bien en llamadas síncronas
(login, buscar cochera, crear un pago). RabbitMQ sí tiene sentido, y es donde este gateway lo
deja preparado, para lo que **ya está diseñado como asíncrono**: `notifications-service`
consumiendo eventos (`booking.confirmed`, `booking.reminder`, `booking.cancelled`,
`payment.completed`) publicados por `booking-service` y `payment-service`. El gateway declara
el exchange compartido y expone un publisher listo para usar; no inventa eventos de negocio
que no le corresponden.

## Qué implementa

### Proxy HTTP

Cada ruta del gateway está mapeada 1:1 (o con un rewrite de prefijo, en el caso de
`payment-service`) a un endpoint real de alguno de los microservicios. La tabla completa vive en
[`app/routes.py`](app/routes.py):

| Prefijo en el gateway | Servicio destino | Notas |
|---|---|---|
| `/auth/*` | `auth-service` | Passthrough completo (registro, login, refresh, sesiones, verificación, reset). |
| `/users/{id}` | `auth-service` | Perfil de identidad (GET/PUT/DELETE). |
| `/users/{id}/parking-spots` | `parking-service` | Cocheras de un dueño. |
| `/users/{id}/bookings/history` | `booking-service` | Histórico de reservas del usuario. |
| `/parking-spots/search`, `/parking-spots/{id}`, `/parking-spots` (POST), `/photos`, `/pricing`, `/schedule`, `/status` | `parking-service` | CRUD y búsqueda de cocheras. |
| `/parking-spots/{id}/availability`, `/parking-spots/{id}/bookings`, `/parking-spots/{id}/reviews` | `booking-service` | Aunque el prefijo es `/parking-spots`, estos sub-recursos son dueños de `booking-service` (ver su README). |
| `/bookings*` | `booking-service` | Crear, consultar, cancelar y reseñar reservas. |
| `/payments/*` | `payment-service` | Reescrito a `/api/payments/*` downstream (así está montado ese servicio). |

`booking-service` todavía no tiene código (solo README). Sus rutas ya están mapeadas acá; con
`BOOKING_SERVICE_URL` vacío (default), el gateway responde `503` en vez de intentar conectarse.
Apenas se despliegue, alcanza con setear esa variable de entorno.

`notifications-service` no se proxea: no expone REST, solo consume eventos de RabbitMQ (push a
los dispositivos), así que el cliente nunca lo llama a través del gateway.

### Autenticación en el borde

El gateway valida el JWT (firma + expiración, mismo `JWT_SECRET`/`JWT_ALGORITHM` que
`auth-service`) para las rutas marcadas `REQUIRED` en la tabla de rutas, **antes** de reenviar
la request. Si es válido:

- Reenvía el header `Authorization` original tal cual (así `auth-service` puede seguir
  haciendo su propia validación completa, con revocación de sesión incluida — el gateway no
  reemplaza esa lógica, solo la adelanta).
- Agrega `X-User-Id: <sub del token>` a la request downstream.

Los servicios leen `X-User-Id` en vez de decodificar el JWT ellos mismos. Para que nadie pueda
mandarles ese header saltándose el gateway, el gateway agrega `X-Gateway-Secret`
(`GATEWAY_INTERNAL_SECRET`) y cada servicio rechaza cualquier request que no lo traiga (o que no
traiga `X-Internal-Key`, la clave para llamadas entre servicios). Para un token de admin, también
agrega `X-Admin-Role`, así los servicios dejan pasar al panel de admin por sus chequeos de dueño.

Si falta el token, es inválido o expiró, el gateway corta con `401` sin llegar a golpear el
servicio downstream.

### RabbitMQ

`app/rabbitmq.py` mantiene una conexión (`aio-pika`, reconexión automática) y declara el
exchange topic compartido `parklink.events` (durable) al arrancar. Si RabbitMQ no está
disponible, el gateway loguea un warning y sigue funcionando igual — el proxy HTTP no depende
de que el broker esté vivo.

Expone `rabbitmq_client.publish_event(routing_key, payload)` para cuando el gateway necesite
publicar algo propio. `booking-service` y `payment-service` van a conectarse al mismo exchange
para publicar `booking.confirmed` / `payment.completed` / etc., y `notifications-service` bindea
sus colas ahí — ver `notifications-service/README.md` para el contrato completo de eventos.

### Otros

- **CORS** configurable vía `CORS_ORIGINS` (default `*`).
- **Timeouts y errores downstream** se traducen a `503`/`504` con el mismo formato
  `application/problem+json` que ya usa `auth-service`, en vez de tirar un 500 genérico.
- **`X-Request-Id`**: se genera (o se respeta si ya viene) por request, se loguea y se reenvía
  downstream, para poder correlacionar logs entre el gateway y los servicios.
- **Health checks**: `/livez`, `/readyz` (mismo estilo que `auth-service`) y `/health`, que
  reporta si RabbitMQ está conectado y qué servicios tienen URL configurada.

## Variables de entorno

Ver [`.env.example`](.env.example). Resumen:

| Variable | Descripción | Default |
|---|---|---|
| `AUTH_SERVICE_URL` / `PARKING_SERVICE_URL` / `PAYMENT_SERVICE_URL` | Base URL de cada servicio | ver `.env.example` |
| `BOOKING_SERVICE_URL` | Base URL de `booking-service`. Vacío = rutas responden 503 | *(vacío)* |
| `JWT_SECRET` / `JWT_ALGORITHM` | Deben coincidir con los de `auth-service` | `dev-secret-change-me` / `HS256` |
| `RABBITMQ_URL` | Connection string de RabbitMQ | `amqp://guest:guest@rabbitmq:5672/` |
| `EVENTS_EXCHANGE` | Exchange topic compartido con el resto de los servicios | `parklink.events` |
| `CORS_ORIGINS` | Orígenes permitidos, separados por coma (`*` = todos) | `*` |
| `UPSTREAM_TIMEOUT_SECONDS` | Timeout al llamar a un servicio downstream | `15` |

## Cómo levantarlo

### Con Docker (recomendado)

```bash
cp .env.example .env
docker compose up --build
```

Esto levanta RabbitMQ (con management UI en `http://localhost:15672`, `guest`/`guest`) y el
gateway (puerto `8080`). Para que el proxy funcione de punta a punta también necesitás
`auth-service`, `parking-service` y/o `payment-service` corriendo (cada uno con su propio
`docker compose up` — ver sus READMEs) y sus URLs apuntadas correctamente en el `.env` del
gateway (usá el hostname del contenedor si están en la misma red de Docker, o `localhost` +
el puerto publicado si corren sueltos).

### Local (sin Docker)

```bash
pip install -r requirements.txt
cp .env.example .env    # apuntar las *_SERVICE_URL a localhost:<puerto> de cada servicio
uvicorn main:app --reload --port 8080
```

Docs interactivas del gateway (no reemplazan las de cada servicio): `http://localhost:8080/docs`.

## Tests

```bash
pip install -r requirements.txt
pytest
```

Los tests no requieren Docker, RabbitMQ ni los otros servicios corriendo: mockean el transporte
HTTP (`httpx.MockTransport`) y toleran que RabbitMQ esté inalcanzable (igual que en producción,
el gateway sigue funcionando sin el broker).

Estructura:

```
tests/
├── conftest.py       # TestClient con transporte HTTP mockeado, helper para firmar JWTs de prueba
├── test_security.py  # validación de JWT (firma, expiración, tipo de token)
├── test_proxy.py      # ruteo correcto por servicio, enforcement de auth, rewrite de /payments, 503 en booking-service
└── test_health.py    # /livez, /readyz, /health
```

## Estructura del proyecto

```
app/
├── config.py       # Settings (pydantic-settings): URLs de servicios, JWT, RabbitMQ, CORS
├── security.py     # Verificación de access tokens JWT (mismo secreto que auth-service)
├── proxy.py         # Forwarding HTTP genérico: headers, rewrite de path, manejo de errores
├── routes.py        # Tabla de rutas (path -> servicio + modo de auth) y su registro en FastAPI
├── rabbitmq.py       # Conexión a RabbitMQ, declaración del exchange, publish_event()
├── middleware.py     # X-Request-Id + logging de acceso
├── problem_json.py   # Respuestas de error en formato application/problem+json
└── logger.py
main.py              # Arma la app: lifespan, CORS, rutas, health checks
```
