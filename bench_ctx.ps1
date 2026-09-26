# Temp benchmark: prefill speed of qwen3:8b under different num_thread values.
# Prefill speed decides how long you wait before the first token in a RAG query.
$API = 'http://127.0.0.1:11434/api/generate'
$unit = [char]0x5411, [char]0x91CF, [char]0x68C0, [char]0x7D22, [char]0x628A, [char]0x6587, [char]0x672C, [char]0x8F6C, [char]0x6362, [char]0x6210, [char]0x5411, [char]0x91CF, [char]0x540E, [char]0x6309, [char]0x76F8, [char]0x4F3C, [char]0x5EA6, [char]0x67E5, [char]0x627E, [char]0x3002 -join ''
$prompt = ($unit * 120) + "`nSummarize the above in one sentence."

foreach ($nt in @(0, 6, 10)) {
    $opts = @{ num_predict = 16 }
    if ($nt -gt 0) { $opts['num_thread'] = $nt }
    $payload = @{ model = 'qwen3:8b'; prompt = $prompt; stream = $false; think = $false; options = $opts }
    $json = $payload | ConvertTo-Json -Compress -Depth 5
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    try {
        $r = Invoke-RestMethod -Uri $API -Method Post -Body $bytes -ContentType 'application/json; charset=utf-8' -TimeoutSec 1200
        $prefill = [math]::Round($r.prompt_eval_count / ($r.prompt_eval_duration / 1e9), 1)
        $gen = [math]::Round($r.eval_count / ($r.eval_duration / 1e9), 2)
        $label = if ($nt -eq 0) { 'default' } else { "num_thread=$nt" }
        "{0,-16} in={1}tok  prefill={2}tok/s  wait={3}s  gen={4}tok/s" -f `
            $label, $r.prompt_eval_count, $prefill, [math]::Round($r.prompt_eval_duration / 1e9, 1), $gen
    } catch {
        "num_thread=$nt failed: $($_.Exception.Message)"
    }
}
