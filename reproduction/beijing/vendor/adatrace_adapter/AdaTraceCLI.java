import java.io.File;
import java.util.List;
import java.util.Locale;

/** Only adapts arguments; upstream synthesis and randomness are untouched. */
public class AdaTraceCLI {
    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.US);
        if (args.length != 3) throw new IllegalArgumentException("input output epsilon");
        if (new File(args[1]).exists()) throw new IllegalArgumentException("Output exists");
        long started = System.nanoTime();
        List<Trajectory> real = Main.readTrajectories(new File(args[0]));
        System.out.println("INPUT_SLOTS=" + real.size());
        List<Trajectory> syn = Main.Synthesize_Trajectories(real, Double.parseDouble(args[2]), false);
        if (syn.size() != real.size()) throw new IllegalStateException("Slot mismatch");
        Main.writeToFile(syn, args[1]);
        System.out.println("FINAL_SLOTS=" + syn.size());
        System.out.println("JAVA_SECONDS=" + (System.nanoTime()-started)/1e9);
    }
}
