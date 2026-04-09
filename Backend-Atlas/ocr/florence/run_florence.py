import sys
import main as florence
import output as out

if __name__ == "__main__":
    image_path = sys.argv[1]
    config = florence.get_runtime_config()
    model, processor = florence.load_model_and_processor(config)
    parsed = florence.run_pipeline(model, processor, image_path, config)
    out.save_result(image_path, parsed)