# -*- coding: utf-8 -*-
"""Modelo 3D y (mas adelante) analisis por elementos finitos de los modulos de conexion (Gmsh + CalculiX).

    builders.build_model(prj) -> Model3D            geometria, pernos y placas del nudo (conn/assembly.py)
    scene.scene_model / render_scene_image          vista 3D y miniaturas (z-buffer propio)
    driver / ccxgen / solve / post / mesher         malla, CalculiX y resultados: SIN USO por ahora (el analisis esta desactivado en los
                                                    modulos nuevos hasta que se ordene reactivarlo)
"""
