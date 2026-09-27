# Yomiba — Bağımsız QA / Test Auditi (2026-09-26)

Kod değiştirilmedi. Migration, cleanup, merge ve deploy yapılmadı. `backend/yomiba.db` yalnızca okundu: SHA-256 değişmedi, cihazdaki mtime değişmedi, `-wal`/`-shm` dosyası oluşmadı. Tüm yazma içeren testler geçici DB'lerde veya DB kopyalarında yapıldı.

---

## 1. EXECUTIVE SUMMARY

- Backend test paketinin tamamı geçiyor: **540 passed**. Frontend typecheck, lint ve production build **PASS**.
- Auth, rol yetkilendirmesi, CSRF (Origin), kullanıcı veri izolasyonu, SQLite sertleştirme, başlangıç sırası ve backup/restore bağımsız olarak doğrulandı ve **PASS**.
- Kimlik güvenliği kuralları bağımsız testlerle doğrulandı ve **PASS**: store import yeni Series/Publisher/Volume üretmiyor, `-1` phantom oluşmuyor, `0` korunuyor, box/set reddediliyor, ISBN conflict reddediliyor.
- Kullanıcıya görünen ciddi sorunlar:
  1. **HIGH:** Legacy `-1` phantom cildleri gerçek ISBN'leri tutuyor. Bu yüzden gerçek cilt (ör. Elveda Eri Cilt 1) ISBN'li mağazalardan listing alamıyor. Phantom'daki listingler de artık güncellenmiyor ve bayat fiyatlar herkese açık gösteriliyor.
  2. **MEDIUM:** Frontend `volume_number=0` değerini “Cilt numarası belirsiz” diye gösteriyor (JJK 0).
  3. **MEDIUM:** Aynı (volume, store) çiftine farklı importlarda farklı ürün bağlanabiliyor. Fiyat A↔B arasında gidip geliyor; sahte fiyat geçmişi ve sahte “indirim” oluşuyor. Snapshot'ta 33 listing etkilenmiş.
  4. **MEDIUM:** Backend erişilemezse ya da `/auth/me` 401 dışında bir hata dönerse **tüm site 500** veriyor (ana sayfa ve login dahil).
  5. **MEDIUM:** Adında sayı geçen seriler eşleşemiyor (Kaiju No: 8, Mob Psycho 100 “Cilt N”, Disney Manga - 6…).
  6. **MEDIUM:** Fiyat yenileme döngüsü çalışırken catalog sync gate'i hiç alamıyor (starvation).

**OVERALL: CONDITIONAL PASS**

---

## 2. TEST ENVIRONMENT

- Kodun salt-okunur kopyası izole bulut çalışma alanına alındı. Cihazdaki Linux VM hazır olmadığı için testler orada koşturulamadı.
- Backend: Python 3.11.15, FastAPI 0.141.1, SQLAlchemy 2.1.1, Alembic 1.20.0, Starlette 1.7.0, argon2-cffi 25.1.0, pytest 9.1.1.
  - Uyarı: `requirements.txt` yalnızca alt sınır veriyor; yüklenen sürümler en günceller.
- Frontend: Node 22.22.2, Next 16.3.4 (Turbopack), `npm ci`.
- Veritabanları:
  - pytest tmp DB'leri.
  - Lokal `yomiba.db`'nin geçici kopyaları (`mig.db`, `rt.db`, `snap.db`). Bunlarla 0004→0005 migration'ı gerçek veride denendi.
  - `backend/yomiba.db` üzerinde yazma yapılmadı.
- Lokal DB snapshot'ı staging'den farklı:
  - Revizyon `0004_catalog_exclusion` (staging `0005`).
  - 60 adet `-1` (staging 75).
  - Series/Catalog/Volume/Listing/History sayıları brief ile aynı: 468/468/2430/4283/4908.
- Railway staging DB'ye erişim **yok**. Staging'e erişim varmış gibi davranılmadı.
- Sandbox kısıtı: `fonts.googleapis.com` egress politikası nedeniyle engelli. Build, `NEXT_FONT_GOOGLE_MOCKED_RESPONSES` ile font mock'lanarak koşturuldu; kod değişmedi.

---

## 3. BACKEND TEST RESULTS

| Grup | Sonuç |
|---|---|
| Auth (`test_auth`) | 5 passed |
| Migration (`test_alembic_upgrade`) | 6 passed |
| Production hardening + Railway staging | 22 passed |
| Scheduler/queue/lock | 43 passed |
| Import/matching (7 dosya) | 101 passed |
| Phantom/AniList audit | 34 passed |
| User data / API / drops | 47 passed |
| **Full suite** | **540 passed**, 10 warning (httpx/starlette deprecation) |

Bağımsız QA probları ayrı bir kopyada, repo'ya yazılmadan koşturuldu:
- 10 auth/izolasyon testi: 9 pass. 1 bulgu (threshold overflow).
- 22 matching testi: hepsi koştu; bulgular bölüm 8 ve 14'te.
- 1 scheduler starvation testi: bulgu.

---

## 4. FRONTEND TEST RESULTS

- `tsc --noEmit`: **PASS**
- `eslint .`: **PASS**
- `next build`: **PASS** (7 route, tamamı dynamic). Font mock yalnızca sandbox için gerekti; Vercel'de Google Fonts erişilebilir.
- Runtime testleri (`next start` + uvicorn `--workers 1`, geçici DB):
  - Home, series, volume, 404 (`/series/999999`, `/series/abc`) ve admin redirect çalışıyor.
  - Login/logout proxy üzerinden çalışıyor.
  - Cookie forwarding çalışıyor.
  - Çıkış yapmış kullanıcıya kişisel state sızmıyor.
- Mobil (Playwright; 360/375/768/1280 genişlik, 7 sayfa): yatay taşma yok.
- Bulunan sorunlar: vol 0 etiketi, backend down / trailing-slash durumunda site geneli 500 (bölüm 14).

---

## 5. AUTH / AUTHORIZATION — PASS

Doğrulananlar:
- register, duplicate email (409), login, yanlış parola (401; olmayan hesapla aynı gövde).
- logout ile sunucu tarafında revoke; revoke edilen token reddediliyor.
- `/auth/me`; expired session ve devre dışı kullanıcı 401 alıyor.
- Argon2id (`$argon2id$`); DB'de yalnızca token SHA-256'sı var; opaque `token_urlsafe(32)`.
- Cookie: `HttpOnly; Secure; SameSite=lax; Path=/`.
- Origin tabanlı CSRF: `evil.example`, `null`, boş, eksik ve sonunda `/` olan origin'lerin hepsi 403.
- Register payload'ındaki `role: "ADMIN"` yok sayılıyor; rol USER oluyor.
- Admin matrisi (8 endpoint: import, coverage, records, price-refresh status/trigger, warmup, catalog sync/status):
  - anonim → **401**
  - USER → **403**
  - ADMIN → **200**

Bulgular: login lockout DoS (M6), logout cookie silme attribute'ları (L2).

---

## 6. DATA ISOLATION — PASS

Test edilen senaryolar:
- User A'nın collection/wishlist/alert verisi User B'ye görünmüyor: volume, series ve per-volume GET uçlarında kontrol edildi.
- B'nin DELETE/PATCH istekleri A'nın verisini değiştirmiyor.
- Status değişimi, kaldırma, geçersiz status (422), alarm pause ve threshold 0 (422) doğru çalışıyor.
- Oturumlu yanıtlar `private, no-store` + `Vary: Cookie`; anonim `/series`, `/volume` yanıtlarında `Vary: Cookie`.
- Next SSR yanıtları `private, no-cache, no-store`.
- Migration 0005 gerçek veri kopyasında: legacy sahipler parolasız, `is_active=0` `legacy-N@yomiba.invalid` hesaplarına bağlanıyor; bu hesaplar login ile ele geçirilemiyor.

---

## 7. CATALOG / IDENTITY

- Search, series ve volume yalnızca `CatalogSeries` içindeki serileri döndürüyor. `%` literal olarak escape ediliyor; boş sorgu 400.
- Store import sonrası Series, Publisher, Volume ve CatalogSeries sayıları değişmiyor (7 başlık × 2 mağaza, yeni yayınevi adıyla denendi).
- `-1` değerlerini Mangakol catalog sync de üretebilir (numarasız Mangakol öğesi). Ancak snapshot'taki 60 `-1` cildin **60'ında da ISBN ve listing var**. Hepsi legacy store phantom'u; catalog kaynaklı `-1` yok.
- AniList runtime bağımlılığı değil: `app/` içinde yalnızca `anilist_audit.py` modülünün kendisi var ve onu yalnızca `audit_phantom_volumes.py` import ediyor.
- `apply_safe_merge` hiçbir yerden çağrılmıyor.
- Offline audit geçici kopyada koşturuldu: 60 aday → 60 REVIEW, 0 SAFE_MERGE, `applied: False`, vol 0 KEEP. DB içeriği değişmedi.

---

## 8. STORE PRODUCT → VOLUME MATCHING

| Kontrol | Sonuç |
|---|---|
| ISBN exact match (farklı başlık/yayınevi) | PASS |
| Publisher/edition izolasyonu (aynı başlık, 2 yayınevi) | PASS; yayınevi olmadan tahmin yok (SKIP) |
| Tek cilt fallback (Solanin/Look Back/Elveda) | PASS |
| Çok ciltte numarasız ürün | PASS (reddediliyor) |
| Volume 0 (JJK 0 ≠ JJK 1) | PASS (backend) |
| `-1` phantom üretilmiyor / hedeflenmiyor | PASS |
| Box/set (“Kutu Seti”, “1-3”, “Bundle”) | PASS (reddediliyor) |
| Aynı run içinde duplicate listing | PASS (en ucuz kazanıyor; 3 run sonunda 1 listing) |
| Yanlış ISBN (katalog ISBN'i farklı) | PASS (`isbn_conflict`) |
| Belirsiz numara (`Cilt 1 Cilt 2`, yıl, fiyat, ISBN parçası) | PASS |
| One Piece 10 format + sentetik 153 sonuç | PASS (62 created + 91 duplicate) |
| Mağaza hatası izolasyonu (403/503) | PASS |
| Fiyat aynı → yeni history yok; değişti → yeni nokta; fiyatsız → nokta yok | PASS |
| **Farklı run'lar arasında A↔B flip** | **FAIL** (M2) |
| **Sayı içeren katalog başlıkları** | **FAIL** (M3) |
| ISBN, başlıktaki numarayla çelişiyor | Tasarım riski (L-ISBN) |

---

## 9. SCHEDULERS / QUEUE — PASS (bulgularla)

- Worker sayısı 2 (sabit), kuyruk kapasitesi 16 (bounded; doluyken submit reddediliyor).
- Per-query dedup ve paylaşımlı kilit çalışıyor.
- Hatalar izole; stale RUNNING kayıtları recover ediliyor. Gerçek veri kopyasında 8 kayıt recover edildi.
- `PriceRefreshScheduler` CatalogSeries üzerinden seçim yapıyor (normalize başlığa göre gruplanıyor). Freshness TTL ve failure-retry çalışıyor.
- Default aralıklar 12 saat / 24 saat.

Bulgular:
- Gate starvation (M4).
- Her restart'ta ilk fiyat döngüsü 12 saat erteleniyor (M8).

---

## 10. SQLITE / STARTUP / SHUTDOWN — PASS

- Gerçek veri kopyasında `APP_ENV=production` ile startup sırası: config → DB reachable → Alembic (0004→0005) → WAL → store seed → stale recovery → readiness (FK check dahil) → runner → schedulers → ready.
- PRAGMA değerleri doğrulandı: `wal`, `foreign_keys=1`, `busy_timeout=30000`.
- Production'da relative path ve var olmayan dosya reddediliyor. Staging'de `/data/yomiba-staging.db` + mount + bootstrap opt-in zorunlu.
- Migration, seed veya readiness hatasında runner ve scheduler başlamıyor (mevcut testler + kod incelemesi).
- `/health` liveness, `/ready` DB+head kontrolü yapıyor. Shutdown sınırlı süre bekliyor.

Risk: dev ortamında startup gerçek lokal DB'yi otomatik migrate ediyor (M7).

---

## 11. BACKUP / RESTORE — PASS

Gerçek verinin geçici kopyasıyla denendi:
- Online backup API: 468/468/2430/4283/4908 sayıları korundu; `quick_check` ok.
- Aynı hedefe ikinci yazma ve kaynağın üzerine yazma reddediliyor (exit 1).
- `restore_check` ok. Kaynak dosya byte-byte aynı kaldı.
- WAL + açık yazma transaction'ı varken alınan backup yalnızca commit edilmiş satırı içeriyor.

---

## 12. FRONTEND / SERVER COMPONENTS / CACHE

- `lib/api.ts`: server tarafında yalnızca `yomiba_session` cookie'si forward ediliyor. Varsayılan `cache: "no-store"`. Series/volume sayfaları `force-dynamic`.
- Kişisel state (collection picker, wishlist, alert) oturum yokken render edilmiyor; login linki gösteriliyor.
- 404: `notFound()` doğru.

Sorunlar:
- **BACKEND_URL join:** `${BACKEND_URL}${path}` ve rewrite `${backend}/:path*` trailing slash'i temizlemiyor. `BACKEND_URL=http://host/` ile SSR `//auth/me` ve `//series/4` isteği atıyor, backend 404 dönüyor, **site geneli 500**. `/api` rewrite'ı bu durumda 200 dönüyor, yani sorun yalnızca SSR'da.
- **500 durumları:** Root layout her istekte `currentUser()` çağırıyor ve 401 dışındaki her hatayı fırlatıyor. `global-error.tsx` yok ve `app/error.tsx` root layout hatalarını yakalamıyor. Sonuç: backend kapalıyken `/`, `/login` ve 404 dahil her sayfa 500 (Next'in varsayılan hata sayfası).

---

## 13. DEPLOYMENT CONFIG AUDIT — UNKNOWN

Koddaki kontrat uyumlu:
- `app.main:app`
- `$PORT`
- `/ready` sağlık kontrolü
- `sqlite:////data/yomiba-staging.db` doğrulaması
- `RAILWAY_VOLUME_MOUNT_PATH=/data` kontrolü
- Staging'de HTTPS `BACKEND_URL`/`CORS_ORIGINS` zorunluluğu
- Secure cookie zorunluluğu

Doğrulanamayanlar:
- Repo'da `railway.json`/`railway.toml` ve `vercel.json` yok. Root Directory, start komutu, `--workers 1`, healthcheck ve volume ayarları yalnızca dashboard'da; koddan doğrulanamaz.
- Kodda tek-process zorunluluğunu uygulayan bir guard yok; `--workers 2` ile sessizce yanlış çalışır.

Kontrat sapmaları:
- `NEXT_PUBLIC_API_BASE` kodda kullanılmıyor (`/api` sabit). Sonucu şu an aynı, ama değişken etkisiz.
- `rewrites()` `BACKEND_URL`'i build zamanında okur. Vercel'de değişken değişince redeploy gerekir.
- Vercel preview origin'leri `CORS_ORIGINS`'te değilse preview'larda tüm yazma istekleri 403 alır.
- Vercel external rewrite'ın `Origin` ve `Set-Cookie` header'larını forward ettiği koddan doğrulanamaz (lokal `next start` ile çalıştı).
- `frontend/pnpm-workspace.yaml` içinde geçersiz placeholder var (`unrs-resolver: set this to true or false`); lockfile npm.

---

## 14. BUGS

### HIGH

**H1 — Phantom `-1` cildler gerçek ISBN'i tutuyor, gerçek cilt aç kalıyor, bayat fiyat yayında**
- **Area:** matching / veri
- **Reproduction:**
  - Gerçek veri kopyasında `GET /series/94` (Elveda Eri) → Cilt 1 (id 327): `store_count=0`. Numarasız cilt (id 5025): 5 mağaza, ₺148.8.
  - QA testi `test_phantom_minus_one_never_created_nor_targeted`: ISBN 9786258237559 → `SKIPPED volume_not_found`.
- **Expected:** Gerçek Cilt 1 fiyatları güncel olarak göstermeli.
- **Actual:**
  - ISBN'li mağazalar (BKM, Kitapsepeti, Kitapbulan, GS, Kitapsec) reddediliyor.
  - Phantom listingleri artık hiç güncellenmiyor ama series/volume sayfasında ve arama cilt sayısında görünüyor ("2 cilt").
  - Snapshot'ta 60 phantom, 176 listing ve 418 history satırı. 46 seride phantom + tek gerçek cilt var.
- **Root cause:** `import_service._resolve_target` ISBN'i phantom'da bulunca reddediyor (doğru, güvenli davranış). Legacy veri temizlenmediği için ISBN phantom'da kilitli kalıyor.
- **Files:** `app/services/import_service.py` (ISBN yolu), veri.
- **Regression risk:** Merge yanlış yapılırsa kullanıcı koleksiyonu ve history bozulur.
- **Recommended fix:**
  - Kod değişikliği değil; onaylı, delil-tabanlı phantom merge gerekiyor (`phantom_review.plan_merge` → manuel onay; önce backup).
  - Kısa vadede API/UI'da `-1` cildleri gizlemek veya "doğrulanmamış" olarak etiketlemek, ve arama cilt sayısından hariç tutmak.

### MEDIUM

**M1 — Volume 0 frontend'de "Cilt numarası belirsiz"**
- **Reproduction:** `/volume/161` (JJK 0). Başlık "Jujutsu Kaisen Cilt 0", gövde "Cilt numarası belirsiz". `/series/4` kartı da aynı.
- **Expected:** "Cilt 0".
- **Root cause:** `number < 1` kontrolü.
- **Files:**
  - `frontend/components/VolumeCard.tsx`
  - `frontend/app/volume/[id]/page.tsx` (ayrıca `null` → "Kutu" metadata'sı, `-1`'in box olduğunu kanıtlamaz)
  - `frontend/components/DropsSection.tsx`
- **Fix:** Yalnızca `number === null` (veya `< 0`) belirsiz sayılmalı; "Kutu" etiketi kaldırılmalı.

**M2 — Farklı importlar arasında ürün flip'i → sahte fiyat geçmişi / sahte indirim**
- **Reproduction:**
  - QA testi `test_cross_run_flip_creates_fake_history`: "Jujutsu Kaisen 0" ₺196.80 ile "Jujutsu Kaisen Cilt 0" ₺472.24 ayrı run'larda geliyor. History: `[19680, 47224, 19680, 47224, 19680]`.
  - Snapshot'ta Kitapbulan listing 3188 aynı deseni gösteriyor; toplam 33 listing'de A-B-A flip var.
  - Volume sayfasındaki grafik zig-zag çiziyor.
- **Expected:** Aynı (volume, store) için ürün kimliği stabil olmalı; fiyat salınımı sahte "drop" üretmemeli.
- **Root cause:** Multi-printing dedup yalnızca tek run içinde yapılıyor. `_upsert_listing` farklı `product_url`'i sorgusuz üzerine yazıp fiyat değişikliğini history'ye ekliyor.
- **Files:** `app/services/import_service.py` (`_upsert_listing`, `run_import`).
- **Fix:**
  - Listing'e ürün kimliği (URL/ISBN) sabitlenmeli. Farklı ürün geldiğinde ya reddedilmeli ya da "en ucuz printing" kararı run'lar arası verilmeli.
  - Mevcut 33 listing'in history'si incelenmeli.

**M3 — Adında sayı geçen seriler eşleşmiyor (false negative)**
- **Reproduction** (`parse_volume_title`):
  - "Kaiju No: 8 - 8 No'lu Canavar 3" → `is_collection=True` ("8 - 8" range sanılıyor) → `box_set`.
  - "Mob Psycho 100 Cilt 2" ve "Dövüş Sınıfı 3 Cilt 2" → `ambiguous_numbers`.
  - "Disney Manga - 6 Süper Kahraman" → vol=6 (başlıktaki 6 cilt sanılıyor).
- **Actual:** Kaiju (8 cilt), Mob Psycho (3), Zom 100 (10), Dövüş Sınıfı 3 ve diğerlerinde 0 listing. Snapshot'ta 468 serinin 248'inde hiç listing yok (hepsi bu nedene bağlı değil).
- **Root cause:** Parser katalog başlığını bilmeden çalışıyor; başlığın içindeki sayılar cilt numarası veya range sanılıyor.
- **Files:** `app/normalization/volume.py`, `app/services/import_service.py`.
- **Fix:** Önce bilinen katalog başlığını (normalize) ürün başlığının başından sıyırıp kalan kısımda numara aramak. Bu seriler için regresyon fixture'ları eklemek.

**M4 — Price refresh sırasında catalog sync gate'i alamıyor (starvation)**
- **Reproduction:** QA testi `test_catalog_gate_starvation...`: kuyruk sürekli doluyken 60/60 non-blocking sync denemesi reddedildi.
- **Actual:** Shared gate'te writer önceliği yok. Scheduler tick'i 900 saniye bekleyip atlanıyor; manuel `POST /catalog/sync` döngü boyunca 409 dönüyor. Tam döngü saatler sürebilir.
- **Files:** `app/services/background_import.py` (`ImportLock`), `app/services/price_refresh_scheduler.py`.
- **Fix:** Bekleyen exclusive istek varken yeni shared acquire'ı durdurmak (writer preference) veya sync tick'inde refresh dispatch'ini duraklatmak.

**M5 — Backend erişilemez / 401 dışı hata → tüm site 500**
- **Reproduction:**
  - Backend kapalıyken `/`, `/login`, `/series/4` → 500 (`__next_error__`).
  - `BACKEND_URL` sonunda `/` varken de aynısı oluyor.
- **Root cause:** `app/layout.tsx` → `currentUser()` 401 dışındaki hatayı fırlatıyor. `global-error.tsx` yok. URL join'de trailing slash normalize edilmiyor.
- **Files:** `frontend/app/layout.tsx`, `frontend/services/auth.ts`, `frontend/lib/api.ts`, `frontend/next.config.ts`.
- **Fix:**
  - Layout'ta hata durumunda `null` kullanıcıya düşmek.
  - `global-error.tsx` eklemek.
  - `BACKEND_URL.replace(/\/+$/, "")`.

**M6 — Hedefli login lockout (DoS)**
- **Reproduction:** Kurbanın e-postasına 10 yanlış deneme yapılınca doğru parola da 429 alıyor (5 dakika).
- **Root cause:** Limiter yalnızca e-posta anahtarlı; IP sinyali bilinçli olarak yok.
- **File:** `app/login_rate_limit.py`.
- **Fix:** Kademeli gecikme veya e-posta+istemci kombinasyonu. Başarılı parola kilitle ezilmemeli ya da captcha/uyarı eklenmeli.

**M7 — Dev startup gerçek lokal DB'yi geri alınamaz şekilde migrate eder**
- **Reproduction** (kod incelemesi; gerçekte çalıştırılmadı): `.env.example` default'u `APP_ENV=development`, `DATABASE_URL=sqlite:///./yomiba.db`. `backend/` içinden `uvicorn app.main:app` çalıştırılırsa gerçek `yomiba.db` 0004→0005'e migrate edilir ve WAL'a çevrilir; downgrade `RuntimeError` verir.
- **Kanıt:** Aynı işlem geçici kopyada denendi ve migrate oldu.
- **Files:** `app/main.py`, `app/database.py`.
- **Fix:** Migration öncesi otomatik online backup, ya da `AUTO_MIGRATE` opt-in / onay bayrağı.

**M8 — Her process restart'ında fiyat yenileme 12 saat erteleniyor**
- `PriceRefreshScheduler.start()` → `next_scheduled_at = now + interval`. Railway'de sık redeploy yapılırsa fiyatlar hiç yenilenmeyebilir.
- **Fix:** `ImportRecord.last_success_at`'e göre catch-up yapmak.

**M9 — Wishlist / koleksiyon "list" yok**
- Yalnızca per-volume GET/POST/DELETE var. Kullanıcı tüm wishlist'ini veya koleksiyonunu listeleyemiyor; frontend'de bunun için sayfa da yok. Brief'teki "list" maddesi karşılanmıyor.
- **Fix:** `GET /me/wishlist`, `GET /me/collection` ve sayfaları.

### LOW

- **L1:** `threshold_price=2**70` → `OverflowError` → 500. Schema'ya üst sınır (`le=`) eklenmeli. (`schemas/price_alert.py`)
- **L-ISBN:** ISBN, başlıktaki numarayla çelişse de kazanıyor ("Gantz 5" + Cilt 1'in ISBN'i → Cilt 1'e bağlanıyor). Mevcut test (`test_isbn_priority_and_conflict`) bunu bilinçli olarak kodluyor; bu yüzden bug değil, tasarım kararı olarak gözden geçirilmeli.
- **L2:** Logout'ta `delete_cookie` Secure/HttpOnly/SameSite attribute'ları olmadan çağrılıyor (session sunucuda zaten revoke).
- **L3:** `PriceAlertForm.toCents("1.500,50")` → ₺1,50.
- **L4:** 422 hatasının `detail` dizisi AuthForm'da ham JSON olarak gösteriliyor.
- **L5:** DropsSection metni "24 saatte bir" diyor; aralık 12 saat.
- **L6:** `NEXT_PUBLIC_API_BASE` etkisiz; `pnpm-workspace.yaml` içinde placeholder.
- **L7:** Süresi dolmuş session'lar temizlenmiyor; register için rate limit yok.
- **L8:** Başlık parse belirsizliği `publisher_conflict` olarak raporlanıyor (yanıltıcı reason).
- **L9:** "Read-only" audit script'i WAL snapshot'ta `-wal`/`-shm` yan dosyaları oluşturuyor (içerik değişmiyor).
- **L10:** `RAILWAY_STAGING.md` "no .git" diyor; kök dizinde `.git` var.

---

## 15. REGRESSION RISKS

- M3 için parser'a katalog-başlığı farkındalığı eklenirse One Piece, JJK 0 ve box fixture'ları kolayca bozulabilir. Mevcut 101 matching testi ve bu auditteki QA probları korunmalı.
- M2 için listing kimliği sabitlenirse, mağaza URL değiştirdiğinde meşru güncellemeler reddedilebilir.
- H1 merge'ü: collection/wishlist/alert FK'leri CASCADE. Yanlış merge kullanıcı verisini silebilir; merge'den önce kullanıcı satırları hedef cilde taşınmalı.
- M5 düzeltmesi: hata durumunda anonim görünüm, oturumlu kullanıcının kişisel state'ini göstermemeli (güvenli yön).
- Bağımlılıklar pinli değil; FastAPI/Starlette majör güncellemeleri middleware sırasını ve TestClient'ı etkileyebilir.

---

## 16. DATA SAFETY

- `backend/yomiba.db`: salt okuma. SHA-256 değişmedi; cihaz mtime `1790325716947`, boyut `3125248`; `-wal`/`-shm` yok.
- Migration, cleanup, merge, WAL değişikliği ve admin bootstrap yapılmadı.
- Tüm yazma testleri geçici DB'lerde yapıldı.
- Railway/Vercel'e erişim veya deploy yok. AniList ve mağaza ağına çağrı yapılmadı (offline).
- Repo'daki hiçbir dosya değiştirilmedi. QA testleri repo dışındaki geçici bir kopyada yazıldı.

---

## 17. FINAL VERDICT

| Alan | Karar |
|---|---|
| BACKEND | **PASS** (540/540; bulgular MEDIUM ve altı) |
| FRONTEND | **FAIL** (build/lint/type PASS; vol 0 kuralı ihlali + site geneli 500) |
| AUTH | **PASS** (M6 not edildi) |
| DATA ISOLATION | **PASS** |
| MATCHING | **PASS** (kimlik güvenliği kuralları); kapsam ve history doğruluğu açıkları M2/M3 |
| SCHEDULER | **PASS** (M4/M8 not edildi) |
| SQLITE | **PASS** |
| BACKUP | **PASS** |
| DEPLOY CONFIG | **UNKNOWN** (dashboard ayarları repo'da yok) |
| **OVERALL** | **CONDITIONAL PASS** — H1 (veri temizliği / gizleme), M1, M2, M5 kapatılmadan production önerilmez |

Kod değiştirilmedi. Fix aşaması için ayrıca onay bekleniyor.
