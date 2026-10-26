# Encode argv for Windows CreateProcess/CPython; Start-Process otherwise joins
# the array without preserving spaces or empty values.
function ConvertTo-NativeArguments {
    param([string[]]$Values)
    $encoded = foreach ($value in $Values) {
        $escaped = [regex]::Replace($value, '(\\*)"', '$1$1\"')
        $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
        '"' + $escaped + '"'
    }
    return ($encoded -join ' ')
}
