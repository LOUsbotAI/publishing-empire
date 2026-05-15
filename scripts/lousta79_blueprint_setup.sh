#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$HOME/lousta79_blueprint"
CORE="$HOME/lousta-core"
SECRETS="$HOME/.lousta_system_core/secrets/.env"
VAULT="$HOME/.lousta_system_core/vault"
mkdir -p "$ROOT" "$ROOT/reports" "$VAULT" "$(dirname "$SECRETS")"
chmod 700 "$HOME/.lousta_system_core" 2>/dev/null || true
touch "$SECRETS" "$ROOT/active_keys_registry.csv" "$ROOT/data_map.csv" "$ROOT/sellable_packs_manifest.csv"
chmod 600 "$SECRETS"
cat > "$ROOT/active_keys_registry.csv" <<'CSV'
key_label,system,environment,masked_prefix,storage_location,status,rule
OPENAI_API_KEY,LouBot/Publishing,live_or_dev,sk-****,~/.lousta_system_core/secrets/.env,NEEDS_KEY,never_store_full_key_in_excel
STRIPE_SECRET_KEY,Stripe API,live,sk_live_****,~/.lousta_system_core/secrets/.env,NEEDS_KEY,confirm_live_vs_test
STRIPE_WEBHOOK_SECRET,Stripe Webhook,live,whsec_****,~/.lousta_system_core/secrets/.env,NEEDS_KEY,rotate_if_exposed
GEMINI_API_KEY,Google AI Studio,dev_or_live,AIza****,~/.lousta_system_core/secrets/.env,NEEDS_KEY,provider_health_check
CLOUDFLARE_API_TOKEN,Cloudflare,live,cf_****,~/.lousta_system_core/secrets/.env,NEEDS_KEY,least_privilege
CSV
cat > "$ROOT/data_map.csv" <<'CSV'
data_item,path_or_endpoint,type,check_command,expected_good_result
webhook_health,http://127.0.0.1:8001/health,http,curl -s http://127.0.0.1:8001/health,200_json
exports_folder,~/lousta-core/output/exports,files,find ~/lousta-core/output/exports -maxdepth 2 -type f | tail,recent_assets
pm2_fleet,pm2 list,process,pm2 list,online_processes
revenue_jsonl,~/.lousta_system_core/vault/revenue_log.jsonl,jsonl,tail -20 ~/.lousta_system_core/vault/revenue_log.jsonl,real_stripe_ids
CSV
cat > "$ROOT/sellable_packs_manifest.csv" <<'CSV'
section,pack_system,product_type,active_key_ref,info,status,data_source,next_step
Publishing,PDF EPUB Pack Generator,Sellable Pack,OPENAI_API_KEY,creates PDF EPUB cover metadata,ACTIVE,~/lousta-core/output/exports,confirm unique assets
Publishing,Audiobook Pack Generator,Sellable Pack,TTS_PROVIDER_KEY,creates MP3 audiobook assets,ACTIVE,~/lousta-core/output/audio,check newest audio
Stripe,Checkout Webhook Receiver,Revenue System,STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET,receives checkout and charge events,ACTIVE,~/lousta_cloud_brain/stripe-webhook/app.py,run health test
Data,Revenue Log,Data Source,STRIPE_WEBHOOK_SECRET,real webhook revenue only,NEEDS_DATA,~/.lousta_system_core/vault/revenue_log.jsonl,filter fake test IDs
CSV
python3 - <<'PY'
import os, json, re, pathlib, datetime
root = pathlib.Path(os.path.expanduser('~/lousta79_blueprint'))
secrets = pathlib.Path(os.path.expanduser('~/.lousta_system_core/secrets/.env'))
wanted = ['OPENAI_API_KEY','STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET','STRIPE_PUBLIC_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','CLOUDFLARE_API_TOKEN']
text = secrets.read_text(errors='ignore') if secrets.exists() else ''
report = []
for key in wanted:
    m = re.search(r'^' + re.escape(key) + r'=(.+)$', text, re.M)
    val = m.group(1).strip().strip('"\'') if m else ''
    masked = (val[:8] + '****' + val[-4:]) if len(val) >= 14 else ('MISSING' if not val else val[:4]+'****')
    status = 'FOUND_MASKED' if val else 'MISSING'
    report.append({'key': key, 'status': status, 'masked': masked, 'length': len(val)})
(root/'reports'/'active_key_audit.json').write_text(json.dumps({'generated': datetime.datetime.now().isoformat(), 'keys': report}, indent=2))
print(json.dumps(report, indent=2))
PY
echo "✅ Lousta79 blueprint created at: $ROOT"
echo "✅ Key audit written to: $ROOT/reports/active_key_audit.json"
echo "⚠️ Only masked key info is printed. Do not paste full secrets into Excel."
