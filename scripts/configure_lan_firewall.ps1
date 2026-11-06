# Opt-in firewall rules for ONE second device on a trusted private LAN.
# Dry-run by default. Run elevated with -Apply only after reviewing the plan.
[CmdletBinding(DefaultParameterSetName = 'Plan')]
param(
    [Parameter(Mandatory = $true)][string]$LocalIp,
    [Parameter(Mandatory = $true)][string]$PeerIp,
    [string]$InterfaceAlias = 'Wi-Fi',
    [Parameter(ParameterSetName = 'Apply')][switch]$Apply,
    [Parameter(ParameterSetName = 'Remove')][switch]$Remove
)
$ErrorActionPreference = 'Stop'

function Get-PrivateIPv4([string]$Value) {
    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($Value, [ref]$parsed) -or
        $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
        $parsed.ToString() -ne $Value) { throw 'Use a plain canonical IPv4 address.' }
    $octets = $parsed.GetAddressBytes()
    if (-not ($octets[0] -eq 10 -or ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
              ($octets[0] -eq 192 -and $octets[1] -eq 168))) { throw 'Only private LAN IPv4 addresses are accepted.' }
    return $parsed
}

$localAddress = Get-PrivateIPv4 $LocalIp
$peerAddress = Get-PrivateIPv4 $PeerIp
if ($LocalIp -eq $PeerIp) { throw 'PeerIp must be the other device, not this laptop.' }
$ruleBase = 'Charcha-LAN-' + $LocalIp.Replace('.', '-') + '-peer-' + $PeerIp.Replace('.', '-')
$ruleNames = @(($ruleBase + '-TCP'), ($ruleBase + '-UDP'))
$plan = [ordered]@{
    action = $(if ($Apply) { 'apply' } elseif ($Remove) { 'remove' } else { 'plan_only' })
    local_ip = $LocalIp; allowed_peer_ip = $PeerIp; interface = $InterfaceAlias
    profile = 'Private'; tcp_ports = @(8443, 8444, 7881); udp_ports = @(7882)
    rules = $ruleNames; provider_calls = 0
}
if (-not $Apply -and -not $Remove) { $plan | ConvertTo-Json -Depth 3; return }

$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Applying or removing the named firewall rules requires an Administrator PowerShell window.'
}
if ($Remove) {
    foreach ($name in $ruleNames) {
        $existing = Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
        if ($existing) { $existing | Remove-NetFirewallRule }
    }
    $plan | ConvertTo-Json -Depth 3
    return
}

$interface = @(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias $InterfaceAlias | Where-Object IPAddress -EQ $LocalIp)
if ($interface.Count -ne 1) { throw 'LocalIp is not uniquely assigned to the selected interface.' }
$profile = @(Get-NetConnectionProfile -InterfaceIndex $interface[0].InterfaceIndex)
if ($profile.Count -ne 1 -or $profile[0].NetworkCategory -ne 'Private') {
    throw 'The selected interface must already be marked Private on a trusted network; no profile is changed automatically.'
}
$prefix = [int]$interface[0].PrefixLength
$localBytes = $localAddress.GetAddressBytes()
$peerBytes = $peerAddress.GetAddressBytes()
for ($bit = 0; $bit -lt $prefix; $bit++) {
    $octet = [int][Math]::Floor($bit / 8)
    $mask = 1 -shl (7 - ($bit % 8))
    if (($localBytes[$octet] -band $mask) -ne ($peerBytes[$octet] -band $mask)) {
        throw 'PeerIp must be in the same directly connected subnet.'
    }
}
foreach ($name in $ruleNames) {
    if (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue) {
        throw 'A named rule already exists. Inspect it or remove this exact pair before applying; no existing rule was overwritten.'
    }
}
$created = @()
try {
    $created += New-NetFirewallRule -Name $ruleNames[0] -DisplayName $ruleNames[0] -Group 'Charcha local test' `
        -Direction Inbound -Action Allow -Enabled True -Profile Private -InterfaceAlias $InterfaceAlias `
        -LocalAddress $LocalIp -RemoteAddress $PeerIp -Protocol TCP -LocalPort 8443,8444,7881 -EdgeTraversalPolicy Block
    $created += New-NetFirewallRule -Name $ruleNames[1] -DisplayName $ruleNames[1] -Group 'Charcha local test' `
        -Direction Inbound -Action Allow -Enabled True -Profile Private -InterfaceAlias $InterfaceAlias `
        -LocalAddress $LocalIp -RemoteAddress $PeerIp -Protocol UDP -LocalPort 7882 -EdgeTraversalPolicy Block
} catch {
    foreach ($rule in $created) { $rule | Remove-NetFirewallRule }
    throw
}
$plan | ConvertTo-Json -Depth 3
