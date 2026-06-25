// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BanRegistry — shared fingerprint and structured ban records for Singulr.
contract BanRegistry {
    address public owner;
    mapping(address => bool) public registrars;

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    modifier onlyRegistrar() {
        require(registrars[msg.sender] || msg.sender == owner, "not registrar");
        _;
    }

    constructor() {
        owner = msg.sender;
        registrars[msg.sender] = true;
    }

    function setRegistrar(address account, bool allowed) external onlyOwner {
        registrars[account] = allowed;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "zero owner");
        owner = newOwner;
    }
    enum BanCategory {
        SPAM,
        SOLICITATION,
        SCAM_FRAUD,
        HARASSMENT,
        BOT_ABUSE,
        IMPERSONATION,
        NSFW,
        RAID_COORDINATION,
        OTHER
    }

    enum BanSeverity {
        LOW,
        MEDIUM,
        HIGH,
        PERMANENT
    }

    enum BanStatus {
        ACTIVE,
        OVERTURNED,
        EXPIRED
    }

    struct FingerprintRecord {
        bool registered;
        uint64 registeredAt;
        uint64 registrantChannel;
    }

    struct BanRecord {
        bytes32 fingerprintHash;
        BanCategory category;
        BanSeverity severity;
        BanStatus status;
        uint64 channelId;
        uint64 bannedAt;
    }

    mapping(bytes32 => FingerprintRecord) public fingerprints;
    mapping(bytes32 => BanRecord[]) private _banHistory;
    mapping(bytes32 => uint256) public activeBanCount;

    event FingerprintRegistered(bytes32 indexed fingerprintHash, uint64 channelId);
    event BanRecorded(
        bytes32 indexed fingerprintHash,
        uint8 category,
        uint8 severity,
        uint64 channelId
    );
    event BanOverturned(bytes32 indexed fingerprintHash, uint256 banIndex);

    function registerFingerprint(bytes32 fingerprintHash, uint64 channelId) external onlyRegistrar {
        require(!fingerprints[fingerprintHash].registered, "already registered");
        fingerprints[fingerprintHash] = FingerprintRecord({
            registered: true,
            registeredAt: uint64(block.timestamp),
            registrantChannel: channelId
        });
        emit FingerprintRegistered(fingerprintHash, channelId);
    }

    function recordBan(
        bytes32 fingerprintHash,
        BanCategory category,
        BanSeverity severity,
        uint64 channelId
    ) external onlyRegistrar {
        _banHistory[fingerprintHash].push(
            BanRecord({
                fingerprintHash: fingerprintHash,
                category: category,
                severity: severity,
                status: BanStatus.ACTIVE,
                channelId: channelId,
                bannedAt: uint64(block.timestamp)
            })
        );
        activeBanCount[fingerprintHash]++;
        emit BanRecorded(fingerprintHash, uint8(category), uint8(severity), channelId);
    }

    function isBanned(bytes32 fingerprintHash) external view returns (bool) {
        return activeBanCount[fingerprintHash] > 0;
    }

    function overturnBan(bytes32 fingerprintHash, uint256 banIndex) external onlyRegistrar {
        BanRecord storage ban = _banHistory[fingerprintHash][banIndex];
        require(ban.status == BanStatus.ACTIVE, "not active");
        ban.status = BanStatus.OVERTURNED;
        activeBanCount[fingerprintHash]--;
        emit BanOverturned(fingerprintHash, banIndex);
    }

    function getReputation(
        bytes32 fingerprintHash
    ) external view returns (uint256 score, uint256 activeBans) {
        activeBans = activeBanCount[fingerprintHash];
        BanRecord[] storage history = _banHistory[fingerprintHash];
        uint256 total = 0;
        for (uint256 i = 0; i < history.length; i++) {
            if (history[i].status == BanStatus.ACTIVE) {
                total += _severityWeight(history[i].severity);
                total += _categoryWeight(history[i].category);
            }
        }
        return (total, activeBans);
    }

    function banHistoryLength(bytes32 fingerprintHash) external view returns (uint256) {
        return _banHistory[fingerprintHash].length;
    }

    function getBanRecord(
        bytes32 fingerprintHash,
        uint256 index
    ) external view returns (BanRecord memory) {
        return _banHistory[fingerprintHash][index];
    }

    function _severityWeight(BanSeverity severity) private pure returns (uint256) {
        if (severity == BanSeverity.PERMANENT) return 100;
        if (severity == BanSeverity.HIGH) return 50;
        if (severity == BanSeverity.MEDIUM) return 25;
        return 10;
    }

    function _categoryWeight(BanCategory category) private pure returns (uint256) {
        if (category == BanCategory.SCAM_FRAUD || category == BanCategory.RAID_COORDINATION) {
            return 50;
        }
        if (category == BanCategory.HARASSMENT || category == BanCategory.IMPERSONATION) {
            return 30;
        }
        return 10;
    }
}
