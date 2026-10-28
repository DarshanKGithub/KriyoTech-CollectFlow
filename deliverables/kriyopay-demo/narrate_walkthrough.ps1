$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$demoNarrator = New-Object System.Speech.Synthesis.SpeechSynthesizer
$demoNarrator.SelectVoice('Microsoft Zira Desktop')
$demoNarrator.Rate = -2
$demoNarrator.Volume = 100
$demoScenes = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'revised/scenes.json') -Raw -Encoding UTF8 | ConvertFrom-Json
for ($demoIndex = 0; $demoIndex -lt $demoScenes.Count; $demoIndex++) {
    $demoNarrator.SetOutputToWaveFile((Join-Path $PSScriptRoot ('revised/audio/{0:00}.wav' -f $demoIndex)))
    $demoNarrator.Speak($demoScenes[$demoIndex].voice)
    $demoNarrator.SetOutputToNull()
}
$demoNarrator.Dispose()
Write-Output 'Slower narration complete. No speech acceleration will be applied.'
