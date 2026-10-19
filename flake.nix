{
  description = "Flake for bruno-bridge using uv2nix";
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
    };
  };

  outputs = {nixpkgs, ...} @ inputs: let
    systems = ["x86_64-linux" "aarch64-darwin"];

    mkVenv = pkgs: let
      python = pkgs.python3;
      workspaceRoot = pkgs.lib.sourceByRegex ./. [
        "pyproject.toml"
        "uv.lock"
        "README.md"
        "src(/.*)?"
      ];
      workspace = inputs.uv2nix.lib.workspace.loadWorkspace {inherit workspaceRoot;};
      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };
      baseSet = pkgs.callPackage inputs.pyproject-nix.build.packages {inherit python;};
      pythonSet = baseSet.overrideScope (
        pkgs.lib.composeManyExtensions [
          inputs.pyproject-build-systems.overlays.default
          overlay
        ]
      );
    in
      pythonSet.mkVirtualEnv "py-venv" (workspace.deps.default
        // {
          bruno-bridge = ["mcp"];
        });
  in {
    devShells = nixpkgs.lib.genAttrs systems (system: {
      default = let
        pkgs = nixpkgs.legacyPackages.${system};
        venv = mkVenv pkgs;
      in (pkgs.mkShell {
        buildInputs = with pkgs; [
          uv
          venv
          basedpyright
          black
        ];
      });
    });
    packages = nixpkgs.lib.genAttrs systems (system: {
      default = let
        pkgs = nixpkgs.legacyPackages.${system};
        venv = mkVenv pkgs;
      in
        pkgs.writeShellApplication {
          name = "brb";
          text = ''
            exec ${venv}/bin/python -m bruno_bridge "$@"
          '';
        };
    });
  };
}
