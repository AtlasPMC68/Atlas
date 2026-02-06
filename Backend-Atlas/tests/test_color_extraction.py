import os
import filecmp
import tempfile
import pytest
from app.utils.color_extraction import extract_colors

# Run with :
# docker-compose run --rm test-backend pytest tests/test_color_extraction.py::TestColorExtraction::test_extract_colors_nouvelle_france_1750 -s --tb=short


class TestColorExtraction:
    
    def test_extract_colors_nouvelle_france_1750(self):
        """
        Test color extraction on Nouvelle-France1750.png.
        
        This test verifies that extraction produces exactly the same results
        as the reference images in tests/assets/color_extraction/.
        
        If this test fails:
        1. Visually check the newly generated images
        2. If they are correct: update the reference images  
        3. If it's a regression: revert the changes
        """
        # Path to source image
        source_image = "tests/assets/Nouvelle-France1750.png"
        assert os.path.exists(source_image), f"Source image missing: {source_image}"
        
        # Expected colors (based on existing reference files)
        expected_colors = {
            "silver_1": "color_1_silver_ratio_0.5010.png",
            "dodgerblue_2": "color_2_dodgerblue_ratio_0.2173.png", 
            "darksalmon_3": "color_3_darksalmon_ratio_0.0829.png",
            "tomato_4": "color_4_tomato_ratio_0.0619.png"
        }
        
        # Reference images directory
        etalons_dir = "tests/assets/color_extraction"
        assert os.path.exists(etalons_dir), f"Reference directory missing: {etalons_dir}"
        
        # Create temporary directory for results (kept after test for inspection)
        temp_output_dir = tempfile.mkdtemp()
        # Run extraction
        result = extract_colors(
            image_path=source_image,
            output_dir=temp_output_dir
        )
        
        # Basic verifications
        assert "colors_detected" in result
        assert "masks" in result
        assert "ratios" in result
        assert "output_dir" in result
        
        # Verify colors were extracted
        colors_detected = result["colors_detected"]
        assert len(colors_detected) > 0, "No colors detected"
        
        print(f"Colors detected: {colors_detected}")
        print(f"Number of colors: {len(colors_detected)}")
        
        issues = []
        
        # Check 1: Expected colors present
        expected_color_names = set(expected_colors.keys())
        detected_color_names = set(colors_detected)
        missing_colors = expected_color_names - detected_color_names
            
            for color in missing_colors:
                issues.append(f"  MISSING: {color} - Not detected in extracted colors")
            
            # Check 2: File comparison for present colors
            for color_name, expected_filename in expected_colors.items():
                if color_name not in colors_detected:
                    continue  # Already reported as missing
                    
                # Verify mask file exists
                assert color_name in result["masks"], f"Mask missing for {color_name}"
                
                # Paths
                generated_file = result["masks"][color_name]
                etalon_file = os.path.join(etalons_dir, expected_filename)
                
                if not os.path.exists(generated_file):
                    issues.append(f"  FILE_MISSING: {color_name} - Generated file not found: {generated_file}")
                    continue
                    
                if not os.path.exists(etalon_file):
                    issues.append(f"  REF_MISSING: {color_name} - Reference file not found: {etalon_file}")
                    continue
                
                # File comparison
                files_identical = filecmp.cmp(generated_file, etalon_file, shallow=False)
                
                if not files_identical:
                    gen_size = os.path.getsize(generated_file)
                    etalon_size = os.path.getsize(etalon_file)
                    issues.append(f"    DIFFERENT: {color_name} - Files differ (gen: {gen_size}B, ref: {etalon_size}B)")
                    issues.append(f"    Generated: {generated_file}")
                    issues.append(f"    Reference: {etalon_file}")
                else:
                    print(f" {color_name}: OK")
            
            # Report all issues at once
            if issues:
                error_msg = f"\n{'='*60}\nCOLOR EXTRACTION TEST FAILED\n{'='*60}\n"
                error_msg += f"Source image: {source_image}\n"
                error_msg += f"Colors detected: {len(colors_detected)}\n"
                error_msg += f"Issues found: {len(issues)}\n\n"
                
                error_msg += "DETAILED ISSUES:\n"
                for issue in issues:
                    error_msg += f"{issue}\n"
                
                error_msg += f"\n{'='*60}\n"
                error_msg += "ACTION REQUIRED:\n"
                error_msg += "1. Check generated images in temp directory\n"
                error_msg += "2. If results are correct: update reference images\n"
                error_msg += "3. If it's a regression: revert changes\n"
                
                pytest.fail(error_msg)
            
            print(f" All {len(expected_colors)} expected colors verified successfully")