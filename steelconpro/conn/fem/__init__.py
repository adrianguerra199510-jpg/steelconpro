# -*- coding: utf-8 -*-
"""Analisis 3D por elementos finitos de las conexiones (Gmsh + CalculiX): modelo, malla, solucion y resultados.

    builders.build_model(prj, vals) -> Model3D       geometria, pernos, cordones, apoyos y cargas de cada tipologia
    driver.run_fem(prj, vals, folder, ...)           malla + CalculiX + resultados (FemResult)
    post.fem_checks(mdl, R, prj)                     verificaciones que salen del analisis
    scene.scene_model / render_scene_png             vista 3D y PNG
"""
