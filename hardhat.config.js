require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.24",
  networks: {
    adiri: {
      url: process.env.CHAIN_RPC || "https://rpc.telcoin.network",
      chainId: parseInt(process.env.CHAIN_ID || "2017", 10),
      accounts: process.env.WALLET_PRIVATE_KEY ? [process.env.WALLET_PRIVATE_KEY] : [],
    },
  },
  paths: {
    sources: "./contracts",
  },
};
