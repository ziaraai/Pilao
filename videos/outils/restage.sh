#!/bin/bash
# Put the demo back as it was before the scenes that change data (pre-fill, status, export).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BID=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['bid'])" "$HERE/state.json")
psql "postgresql://pilao:pilao@localhost:5432/pilao_demo" -q <<SQL
delete from human_resources; delete from equipment; delete from certifications;
update profile_suggestions set status = 'pending' where kind in ('human_resource','equipment','certification');
update profile_suggestions set data = jsonb_set(data, '{count}', 'null'::jsonb), missing = array['count']
  where kind = 'human_resource' and data->>'qualification' = 'Responsable d''exploitation';
update bids set status = 'to_review' where id = '$BID';
delete from generated_documents where bid_id = '$BID' and kind = 'bundle_zip';
SQL
echo restaged
