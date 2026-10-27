#!/usr/bin/env bash
set -e

PORT=4000
TOKEN="autorepro_secret_token_123"
URL="http://127.0.0.1:${PORT}"

echo "1. Checking /health..."
HEALTH=$(curl -s "${URL}/health")
echo "Health: ${HEALTH}"

echo "2. Testing Auth: /provision without token (should be 401)..."
UNAUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${URL}/provision" -H "Content-Type: application/json" -d '{"version":"v1.0.0"}')
echo "Unauth HTTP code: ${UNAUTH_CODE}"
if [ "${UNAUTH_CODE}" != "401" ]; then echo "FAILED: expected 401"; exit 1; fi

echo "3. Testing Input Validation: malicious version injection (should be 400)..."
INJECT_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${URL}/provision" -H "Content-Type: application/json" -H "X-Auth-Token: ${TOKEN}" -d '{"version":"v1.0.0; rm -rf /"}')
echo "Inject HTTP code: ${INJECT_CODE}"
if [ "${INJECT_CODE}" != "400" ]; then echo "FAILED: expected 400"; exit 1; fi

echo "4. Testing Input Validation: non-existent version (should be 400)..."
NOEXIST_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${URL}/provision" -H "Content-Type: application/json" -H "X-Auth-Token: ${TOKEN}" -d '{"version":"v9.9.9"}')
echo "Non-existent HTTP code: ${NOEXIST_CODE}"
if [ "${NOEXIST_CODE}" != "400" ]; then echo "FAILED: expected 400"; exit 1; fi

echo "5. Testing /provision with valid v1.1.0 and issue 42..."
PROV_RES=$(curl -s -X POST "${URL}/provision" -H "Content-Type: application/json" -H "X-Auth-Token: ${TOKEN}" -d '{"version":"v1.1.0","issue_number":42}')
echo "Provision response: ${PROV_RES}"

RUN_ID=$(echo "${PROV_RES}" | node -e 'let d = ""; process.stdin.on("data", c => d += c); process.stdin.on("end", () => console.log(JSON.parse(d).run_id));')
PUBLIC_URL=$(echo "${PROV_RES}" | node -e 'let d = ""; process.stdin.on("data", c => d += c); process.stdin.on("end", () => console.log(JSON.parse(d).public_url));')

echo "Provisioned run_id: ${RUN_ID}"
echo "Provisioned URL: ${PUBLIC_URL}"

echo "6. Testing Container Health via public_url..."
CONTAINER_VER=$(curl -s "${PUBLIC_URL}/version")
echo "Container version endpoint: ${CONTAINER_VER}"
if [ "${CONTAINER_VER}" != "v1.1.0" ]; then echo "FAILED: unexpected container version"; exit 1; fi

echo "7. Testing /events..."
EVENT_RES=$(curl -s -X POST "${URL}/events" -H "Content-Type: application/json" -H "X-Auth-Token: ${TOKEN}" -d "{\"run_id\":\"${RUN_ID}\",\"stage\":\"TEST_STEP\",\"message\":\"Running curl test\"}")
echo "Event response: ${EVENT_RES}"

echo "8. Testing /teardown..."
TEARDOWN_RES=$(curl -s -X POST "${URL}/teardown" -H "Content-Type: application/json" -H "X-Auth-Token: ${TOKEN}" -d "{\"run_id\":\"${RUN_ID}\"}")
echo "Teardown response: ${TEARDOWN_RES}"

echo "9. Verifying Docker containers destroyed..."
REMAINING=$(docker ps -q --filter "label=autorepro=true" | wc -l | tr -d ' ')
echo "Remaining containers with autorepro=true: ${REMAINING}"
if [ "${REMAINING}" != "0" ]; then echo "FAILED: containers still running!"; exit 1; fi

echo "==> STEP 2 ALL VERIFICATIONS PASSED!"
