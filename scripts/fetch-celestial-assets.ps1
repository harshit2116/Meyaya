$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot '../bot/assets/celestial'
New-Item -ItemType Directory -Force -Path "$root/tarot", "$root/kenney" | Out-Null
$deck = @('Fool','Magician','High Priestess','Empress','Emperor','Hierophant','Lovers','Chariot','Strength','Hermit','Wheel of Fortune','Justice','Hanged Man','Death','Temperance','Devil','Tower','Star','Moon','Sun','Judgement','World')
foreach ($i in 0..21) {
    $target = Join-Path $root ('tarot/{0:d2}.jpg' -f $i)
    if (Test-Path -LiteralPath $target) { continue }
    $name = 'RWS Tarot {0:d2} {1}.jpg' -f $i,$deck[$i]
    $page = Invoke-WebRequest -UseBasicParsing -Uri ('https://commons.wikimedia.org/wiki/File:' + [Uri]::EscapeDataString($name)) -TimeoutSec 30
    if ($page.Content -notmatch 'public domain') { throw "License not verified for $name" }
    $url = [regex]::Match($page.Content, 'href="(https://upload\.wikimedia\.org/wikipedia/commons/[^" ]+\.jpg)"').Groups[1].Value
    if (-not $url) { throw "Original file missing: $name" }
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $target -TimeoutSec 60
    Write-Output "Downloaded $name"
}
$zip = Join-Path $root 'kenney/fantasy-ui.zip'
if (-not (Test-Path -LiteralPath $zip)) {
    Invoke-WebRequest -UseBasicParsing 'https://kenney.nl/media/pages/assets/fantasy-ui-borders/ab29cd0165-1701602367/kenney_fantasy-ui-borders.zip' -OutFile $zip -TimeoutSec 60
}
Expand-Archive -LiteralPath $zip -DestinationPath "$root/kenney" -Force
