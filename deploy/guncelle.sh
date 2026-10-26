#!/usr/bin/env bash
# Yomiba — testten geçmiş bir commit'i sunucuya al ve yeniden başlat.
#   /srv/yomiba/app/deploy/guncelle.sh            # elle: GitHub'daki son main
#   /srv/yomiba/app/deploy/guncelle.sh <sha>      # elle: o commit
# GitHub Actions da main'e push'ta (testler geçince), haftada bir ve elle
# başlatılınca SSH ile bunu çalıştırır (.github/workflows/deploy.yml) ve
# "deploy <40 haneli sha>" gönderir: sunucu tam o commit'e geçer, ondan
# daha yenisine asla. O anahtar yalnızca bu betiği çalıştırabilir.
set -euo pipefail
cd "$(dirname "$0")"
SELF="$PWD/$(basename "$0")"

if [ "${1:-}" != "--cekildi" ]; then
  # Zorunlu komutla (authorized_keys command=) gelen istek SSH_ORIGINAL_COMMAND'da.
  if [ -n "${SSH_ORIGINAL_COMMAND:-}" ]; then
    case "$SSH_ORIGINAL_COMMAND" in
      "deploy "*) hedef="${SSH_ORIGINAL_COMMAND#deploy }" ;;
      *) echo "HATA: beklenen komut 'deploy <sha>'"; exit 2 ;;
    esac
  else
    hedef="${1:-}"
  fi
  if [ -n "$hedef" ] && ! [[ "$hedef" =~ ^[0-9a-f]{40}$ ]]; then
    echo "HATA: sha 40 haneli olmalı: $hedef"; exit 2
  fi

  # Aynı anda iki deploy olmasın; kilit exec sonrasında da tutulur.
  exec 9>/var/lock/yomiba-deploy.lock
  flock 9
  git -C .. fetch --quiet origin main
  if [ -z "$hedef" ]; then
    hedef="$(git -C .. rev-parse origin/main)"
    echo "UYARI: sha verilmedi, GitHub'daki son main alınıyor: ${hedef:0:7}"
  fi
  if ! git -C .. merge-base --is-ancestor "$hedef" origin/main; then
    echo "HATA: ${hedef:0:7} GitHub'daki main'de yok"; exit 1
  fi
  simdiki="$(git -C .. rev-parse HEAD)"
  if [ "$simdiki" != "$hedef" ] && git -C .. merge-base --is-ancestor "$hedef" "$simdiki"; then
    # Sıra karışırsa (eski commit'in işi yenisinden sonra gelirse) geri gitme.
    echo "sunucu zaten daha yeni bir sürümde (${simdiki:0:7}); ${hedef:0:7} atlandı"
    echo "DEPLOY_ATLANDI=$simdiki"
    exit 0
  fi
  git -C .. merge --quiet --ff-only "$hedef"
  # Bash betiği okurken çalıştırır: yeni sürümüyle baştan devam et.
  exec "$SELF" --cekildi "$hedef"
fi

hedef="${2:-}"
if [ -z "$hedef" ]; then
  # Eski guncelle.sh bu sürüme `git pull` ile geçince sha'yı vermez; o tek
  # seferlik geçişte iş akışının istediği commit SSH_ORIGINAL_COMMAND'da.
  istek="${SSH_ORIGINAL_COMMAND:-}"
  hedef="${istek#deploy }"
  [[ "$hedef" =~ ^[0-9a-f]{40}$ ]] || hedef="$(git -C .. rev-parse HEAD)"
fi
simdiki="$(git -C .. rev-parse HEAD)"
if [ "$simdiki" != "$hedef" ]; then
  echo "HATA: sunucudaki commit ${simdiki:0:7}, istenen ${hedef:0:7}"; exit 1
fi

echo "sürüm: $(git -C .. log -1 --format='%h %s')"
# İmajlara commit etiketi (org.opencontainers.image.revision) yazılır;
# aşağıda çalışan konteynerlerin bu commit'ten olduğu kontrol edilir.
export YOMIBA_REVISION="$hedef"
docker compose build --pull
docker compose up -d --wait --wait-timeout 300
for servis in backend frontend; do
  kimlik="$(docker compose ps -q "$servis")"
  # Etiketi konteynerin kendisinden oku: imaj aynı commit'ten yeniden
  # yapılınca (haftalık deploy) compose konteyneri değiştirmez, ama imaj adı
  # yeni yapıya geçtiği için konteynerin eski imaj kimliği artık bulunamaz.
  etiket="$(docker inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$kimlik")"
  if [ "$etiket" != "$hedef" ]; then
    echo "HATA: $servis konteyneri ${etiket:-etiketsiz} imajıyla çalışıyor, beklenen ${hedef:0:7}"
    docker compose ps
    exit 1
  fi
done
docker image prune -f >/dev/null
domain="$(sed -n 's/^SITE_DOMAIN=//p' .env)"
# Frontend'in sağlık kontrolü yok: --wait onu "çalışıyor" görür görmez
# bırakır, Next ise birkaç saniye sonra dinlemeye başlar (o arada Caddy 502
# döner). Bir dakika boyunca tekrar dene.
for i in $(seq 1 12); do
  curl -fsS -o /dev/null --max-time 20 "https://${domain:-yomiba.net}/" && break
  [ "$i" = 12 ] && { echo "HATA: site cevap vermiyor"; docker compose ps; exit 1; }
  sleep 5
done
docker compose ps
echo "DEPLOY_SHA=$hedef"
echo "deploy tamam"
