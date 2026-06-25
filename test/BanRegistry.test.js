const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("BanRegistry", function () {
  const fingerprint = ethers.id("test-fingerprint");

  async function deployRegistry() {
    const BanRegistry = await ethers.getContractFactory("BanRegistry");
    return BanRegistry.deploy();
  }

  it("registers a fingerprint", async function () {
    const registry = await deployRegistry();
    await registry.registerFingerprint(fingerprint, 42);
    const record = await registry.fingerprints(fingerprint);
    expect(record.registered).to.equal(true);
    expect(record.registrantChannel).to.equal(42n);
  });

  it("records ban and isBanned reflects active count", async function () {
    const registry = await deployRegistry();
    await registry.recordBan(fingerprint, 2, 3, 99); // SCAM_FRAUD, PERMANENT
    expect(await registry.isBanned(fingerprint)).to.equal(true);
    expect(await registry.activeBanCount(fingerprint)).to.equal(1n);
  });

  it("getReputation returns score and active ban count", async function () {
    const registry = await deployRegistry();
    await registry.recordBan(fingerprint, 2, 3, 99);
    const [score, activeBans] = await registry.getReputation(fingerprint);
    expect(activeBans).to.equal(1n);
    expect(score).to.be.gt(0n);
  });

  it("overturnBan deactivates a ban", async function () {
    const registry = await deployRegistry();
    await registry.recordBan(fingerprint, 8, 0, 1); // OTHER, LOW
    await registry.overturnBan(fingerprint, 0);
    expect(await registry.isBanned(fingerprint)).to.equal(false);
    const ban = await registry.getBanRecord(fingerprint, 0);
    expect(ban.status).to.equal(1n); // OVERTURNED
  });

  it("rejects non-registrar recordBan", async function () {
    const registry = await deployRegistry();
    const [, stranger] = await ethers.getSigners();
    await expect(
      registry.connect(stranger).recordBan(fingerprint, 8, 0, 1)
    ).to.be.revertedWith("not registrar");
  });
});
