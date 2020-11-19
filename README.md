# Debt manager backend
##### Бекенд проекта debt manager.
## Запуск dev docker контейнера
`docker-compose -f ./docker-compose-dev.yml up`
## Запуск боевого docker контейнера
`docker-compose up`
## Переменные контейнера:
0. SECRET_KEY - секретный ключ для django
0. GOOGLE_RECAPTCHA_SECRET_KEY - секретный ключ для recaptcha v3
0. FRONT_MAIN_PAGE - адрес для редиректа при подтверждении емаила после регистрации
0. EMAIL_USE_TLS - использовать tls, принимает любое значение как True
0. EMAIL_HOST - хост smtp сервера
0. EMAIL_HOST_USER - пользователь smtp сервера
0. EMAIL_HOST_PASSWORD - пароль для пользователя smtp сервера
0. EMAIL_FROM - почтовый адрес отправителя
0. EMAIL_PORT - порт smtp сервера
0. CORS_ORIGIN_REGEX_WHITELIST - список regexp выражений с разрешенными CORS url, обязательно экранирование \, привер значения `["http://localhost:?[\\d]{0,5}"]`
0. POSTGRES_DB - имя бд проекта (должно быть одинаковым у сервисов debt-manager и db)
0. POSTGRES_USER - имя пользователя бд проекта (должно быть одинаковым у сервисов debt-manager и db)
0. POSTGRES_PASSWORD - пароль пользователя бд проекта (должно быть одинаковым у сервисов debt-manager и db)
0. DEBUG - дебаг режим для django, принимает любое значение как True. **Не устанавливать в боевом контейнере**
0. ADMIN_NAME - имя учетной записи администратора для управления через django admin panel
0. ADMIN_EMAIL - email администратора django
0. ADMIN_NAME - пароль администратора django

## После сборки проекта необходимо создать clientId и clientSecret
0. Зайтив панель администартора django /admin/
0. Создать новой приложение /api/auth/applications/
    0. Name - произвольное имя приложения
    0. Client type - confidential
    0. Authorization grant type - password
