const hre = require("hardhat");

async function main() {
  const BanRegistry = await hre.ethers.getContractFactory("BanRegistry");
  const registry = await BanRegistry.deploy();
  await registry.waitForDeployment();
  const address = await registry.getAddress();
  console.log("BanRegistry deployed to:", address);
  console.log("Explorer:", `${process.env.CHAIN_EXPLORER || "https://telscan.io"}/address/${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
