#!/usr/bin/env bash
# Full memory-system suite AFTER code-review fixes (H1/H2/L1/M1 + M2/M3/M4 tests).
PY="/c/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")"
echo "=== compile ==="
"$PY" -m py_compile \
  backend/core/settings.py \
  backend/database/models.py \
  backend/flows/customer_flow.py \
  backend/services/active_constraints_loader.py \
  backend/repositories/chat_message_repository.py \
  backend/repositories/session_repository.py \
  backend/services/conversation_distillate_service.py \
  backend/services/cross_conv_recall_service.py \
  backend/services/chat_message_purge_service.py \
  backend/tests/unit/test_conversation_distillate.py \
  backend/tests/unit/test_cross_conv_recall.py \
  backend/tests/unit/test_chat_message_purge.py \
  backend/tests/unit/test_customer_flow_memory_context.py \
  backend/tests/integration/test_customer_memory_wireup.py
echo "COMPILE_OK"
echo "=== tasks.yaml parses + has cross_conv_context inline ==="
"$PY" -c "import yaml; d=yaml.safe_load(open('backend/agents/customer/config/tasks.yaml',encoding='utf-8')); s=d['search_task']['description']+d['explanation_task']['description']; assert '{cross_conv_context}' in s; print('YAML_OK')"
echo "=== full unit suite ==="
PYTHONPATH=backend "$PY" -m pytest backend/tests/unit/ -q -p no:warnings 2>&1 | tail -5
echo "=== integration (non-destructive: skips the global purge_now(1) test) ==="
PYTHONPATH=backend "$PY" -m pytest backend/tests/integration/test_customer_memory_wireup.py \
  -k "not test_purge_deletes_stale_rows" -q -p no:warnings 2>&1 | tail -5
