[CmdletBinding()]
param(
    [int[]]$Seeds = @(20260719, 20260720, 20260721, 20260722, 20260723),
    [double[]]$Epsilons = @(0.2, 0.4, 0.7, 1.0, 1.4, 2.0, 3.0),
    [int]$Slots = 17123,
    [int]$ResolutionK = 8
)

$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$InputRoot = Join-Path $Repo '..\..\check\github_clean_repro_20260925'
$Matched = Join-Path $InputRoot 'derived\real_road_reference\matched_paths\Real.pkl.gz'
$Real = Join-Path $InputRoot 'input\real_full_frozen.pkl'
$Osm = Join-Path $InputRoot 'evaluation\data\osm\osm_cache_beijing.pkl'
$EdgeCache = Join-Path $Repo 'public_assets\ordered_portal_route_cache.pkl.gz'
$Network = Join-Path $Repo 'public_assets\beijing_network\network.shp'
$OutRoot = Join-Path $Repo 'experiment_results\sensitivity\local_budget'
$LogRoot = Join-Path $OutRoot 'logs'
New-Item -ItemType Directory -Force $OutRoot, $LogRoot | Out-Null

foreach ($seed in $Seeds) {
    foreach ($eps in $Epsilons) {
        $epsTag = ('{0:0.0}' -f $eps).Replace('.', '_')
        $tag = "eps_${epsTag}_seed${seed}"
        $run = Join-Path $OutRoot $tag
        $manifest = Join-Path $run "seed_${seed}_length\manifest.json"
        $log = Join-Path $LogRoot "${tag}.log"
        if (Test-Path $manifest) {
            Add-Content $log "SKIP existing manifest: $manifest"
            continue
        }
        try {
            Add-Content $log "START $tag $(Get-Date -Format o)"
            & python (Join-Path $Repo 'generation\mtr_dfr\run.py') `
                --real-matched $Matched --edge-cache $EdgeCache --network $Network `
                --seed $seed --length-aware --public-slot-count $Slots `
                --resolution-k $ResolutionK --epsilon-total $eps --out-dir $run `
                *>> $log
            $routes = Join-Path $run "seed_${seed}_length\road_routes.pkl.gz"
            $coords = Join-Path $OutRoot "${tag}_coordinates.pkl"
            & python (Join-Path $Repo 'commands\reproduce.py') routes-to-coordinates -- `
                --routes $routes --network $Network --edge-cache $EdgeCache --out $coords `
                *>> $log
            $profile = Join-Path $OutRoot "profile_${tag}"
            & python (Join-Path $Repo 'commands\reproduce.py') run-profile -- `
                --real $Real --bbox 39.75 40.15 116.10 116.65 --osm-cache $Osm `
                --public-slot-count $Slots --synthetic "MTR-DFR=$coords" `
                --road-routes "MTR-DFR=$routes" --edge-cache $EdgeCache --out-dir $profile `
                *>> $log
            Add-Content $log "DONE $tag $(Get-Date -Format o)"
        } catch {
            Add-Content $log "FAILED $tag $($_.Exception.Message)"
            throw
        }
    }
}
