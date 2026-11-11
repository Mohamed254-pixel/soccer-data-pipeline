#!/usr/bin/env bash
(
set -euo pipefail

app_password=$(cat /run/secrets/demo_app)
bootstrap_password=$(cat /run/secrets/demo_bootstrap)
for password in "$app_password" "$bootstrap_password"; do
    [[ $password =~ ^[a-f0-9]{64}$ ]] || exit 1
done
MYSQL_PWD="$(cat /run/secrets/demo_root)" mysql --protocol=socket -uroot --database=soccer_db <<SQL
CREATE USER 'demo_app'@'%' IDENTIFIED BY '${app_password}' REQUIRE SSL;
GRANT SELECT, INSERT, UPDATE, DELETE ON soccer_db.* TO 'demo_app'@'%';
CREATE USER 'demo_bootstrap'@'%' IDENTIFIED BY '${bootstrap_password}' REQUIRE SSL;
GRANT ALL PRIVILEGES ON soccer_db.* TO 'demo_bootstrap'@'%';
SQL
)
